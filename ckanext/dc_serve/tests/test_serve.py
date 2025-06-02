import copy
import json
import pathlib
from unittest import mock
import shutil
import time
import uuid

import ckan.tests.factories as factories
import dclab
from dclab.rtdc_dataset import fmt_http
import h5py

import pytest

from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job
from dcor_shared import s3cc


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
def test_auth_forbidden(app):
    user2 = factories.UserWithToken()

    # create a dataset
    _, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True,
        private=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "valid",
                },
        headers={u"authorization": user2["token"]},
        status=403
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "not authorized to read resource" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_error(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(
        users=[{'name': user['id'],
                'capacity': 'admin'}]
    )
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    # missing query parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"]},
        headers={"Authorization": user["token"]},
        status=409
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'query' parameter" in jres["error"]["message"]

    # missing id parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "feature"},
        headers={"Authorization": user["token"]},
        status=409
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'id' parameter" in jres["error"]["message"]

    # bad ID
    bid = str(uuid.uuid4())
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "feature_list",
                "id": bid,
                },
        headers={"Authorization": user["token"]},
        status=404
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Not found" in jres["error"]["message"]

    # invalid query
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "peter",
                "id": res_dict["id"],
                },
        headers={"Authorization": user["token"]},
        status=409
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Invalid query parameter 'peter'" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin(enqueue_job_mock, app, tmp_path):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    # create a dataset
    path_orig = data_path / "calibration_beads_47.rtdc"
    path_test = tmp_path / "calibration_beads_47_test.rtdc"
    shutil.copy2(path_orig, path_test)
    with dclab.RTDCWriter(path_test) as hw:
        hw.store_basin(basin_name="example basin",
                       basin_type="remote",
                       basin_format="http",
                       basin_locs=["http://example.org/peter/pan.rtdc"],
                       basin_descr="an example test basin",
                       verify=False,  # does not exist
                       )

    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=path_test,
        activate=True,
        private=False,
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "basins",
                },
        headers={"Authorization": user["token"]},
        status=200
    )

    jres = json.loads(resp.body)
    assert jres["success"]
    # Fetch the http resource basin
    for bn_dict in jres["result"]:
        if bn_dict["name"] == "resource":
            break

    with fmt_http.RTDC_HTTP(bn_dict["urls"][0]) as ds:
        basin = ds.basins[0].as_dict()
        assert basin["basin_name"] == "example basin"
        assert basin["basin_type"] == "remote"
        assert basin["basin_format"] == "http"
        assert basin["basin_descr"] == "an example test basin"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin_v2(enqueue_job_mock, app, tmp_path):
    user = factories.UserWithToken()
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    _, res_dict1 = make_dataset_via_s3(
        create_context=copy.deepcopy(create_context),
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    s3_url = res_dict1["s3_url"]

    # create a dataset
    path_orig = data_path / "calibration_beads_47.rtdc"
    path_test = tmp_path / "calibration_beads_47_test.rtdc"
    shutil.copy2(path_orig, path_test)

    with h5py.File(path_test) as h5:
        # sanity check
        assert "deform" in h5["events"]

    with dclab.RTDCWriter(path_test) as hw:
        hw.store_basin(basin_name="example basin",
                       basin_type="remote",
                       basin_format="s3",
                       basin_locs=[s3_url],
                       basin_descr="an example test basin",
                       verify=True,
                       )
        del hw.h5file["events/deform"]

    with h5py.File(path_test) as h5:
        # sanity check
        assert "deform" not in h5["events"]

    ds_dict, res_dict = make_dataset_via_s3(
        create_context=copy.deepcopy(create_context),
        resource_path=path_test,
        activate=True)

    rid = res_dict["id"]

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "feature_list",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 0

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "feature",
                "feature": "area_um",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=409  # ValidationError
    )
    jres = json.loads(resp.body)
    assert not jres["success"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "basins",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]

    # The dcserv API only returns the basins it itself creates (The S3 basins,
    # but it does not recurse into the files on S3, so the original basin
    # that we wrote in this test is not available; only the remote basins).
    basins = jres["result"]
    assert len(basins) == 2
    for bn in basins:
        assert bn["type"] == "remote"
        assert bn["format"] == "http"
        assert bn["name"] in [f"condensed-{rid[:5]}", f"resource-{rid[:5]}"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin_v2_public_not_signed(enqueue_job_mock, app):
    user = factories.UserWithToken()
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    _, res_dict = make_dataset_via_s3(
        create_context=copy.deepcopy(create_context),
        resource_path=data_path / "calibration_beads_47.rtdc",
        private=False,
        activate=True)
    rid = res_dict["id"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "basins",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    basins = jres["result"]

    for bn in basins:
        assert bn["type"] == "remote"
        assert bn["format"] == "http"
        assert not bn["perishable"]
        for url in bn["urls"]:
            assert not url.lower().count("expires")

    bn_cond = basins[0]
    bn_res = basins[1]

    assert bn_res["name"] == f"resource-{rid[:5]}"
    assert "deform" in bn_res["features"]
    assert "image" in bn_res["features"]
    assert len(bn_res["features"]) == 34
    assert bn_res["urls"][0] == s3cc.get_s3_url_for_artifact(rid, "resource")

    assert bn_cond["name"] == f"condensed-{rid[:5]}"
    assert "deform" in bn_cond["features"]
    assert "image" not in bn_cond["features"]
    assert "volume" in bn_cond["features"]
    assert bn_cond["urls"][0] == s3cc.get_s3_url_for_artifact(rid, "condensed")


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin_v2_private_presigned(enqueue_job_mock, app):
    user = factories.UserWithToken()
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    _, res_dict = make_dataset_via_s3(
        create_context=copy.deepcopy(create_context),
        resource_path=data_path / "calibration_beads_47.rtdc",
        private=True,
        activate=True)
    rid = res_dict["id"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "basins",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    basins = jres["result"]

    for bn in basins:
        assert bn["type"] == "remote"
        assert bn["format"] == "http"
        assert bn["perishable"]
        for url in bn["urls"]:
            assert url.lower().count("expires")

    bn_cond = basins[0]
    bn_res = basins[1]

    assert bn_res["name"] == f"resource-{rid[:5]}"
    assert "deform" in bn_res["features"]
    assert "image" in bn_res["features"]
    assert len(bn_res["features"]) == 34

    assert bn_cond["name"] == f"condensed-{rid[:5]}"
    assert "deform" in bn_cond["features"]
    assert "image" not in bn_cond["features"]
    assert "volume" in bn_cond["features"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin_v2_private_presigned_expiration_time(
        enqueue_job_mock, app):
    user = factories.UserWithToken()
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    _, res_dict = make_dataset_via_s3(
        create_context=copy.deepcopy(create_context),
        resource_path=data_path / "calibration_beads_47.rtdc",
        private=True,
        activate=True)
    rid = res_dict["id"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "basins",
                "version": "2",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    basins = jres["result"]

    for bn in basins:
        assert bn["type"] == "remote"
        assert bn["format"] == "http"
        assert bn["perishable"]
        assert bn["time_request"] < time.time()
        assert bn["time_expiration"] > time.time() + 3000
        for url in bn["urls"]:
            assert url.lower().count("expires")

    bn_cond = basins[0]
    bn_res = basins[1]

    assert bn_res["name"] == f"resource-{rid[:5]}"
    assert "deform" in bn_res["features"]
    assert "image" in bn_res["features"]
    assert len(bn_res["features"]) == 34

    assert bn_cond["name"] == f"condensed-{rid[:5]}"
    assert "deform" in bn_cond["features"]
    assert "image" not in bn_cond["features"]
    assert "volume" in bn_cond["features"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_feature_list(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "feature_list",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 0, "deprecated"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_logs(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "logs",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["hans"][0] == "peter"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_metadata(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "metadata",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["setup"]["channel width"] == 20


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_size(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "size",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert jres["result"] == len(ds)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_tables(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "cytoshot_blood.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "tables",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert "src_cytoshot_monitor" in jres["result"]
    names, data = jres["result"]["src_cytoshot_monitor"]
    assert "brightness" in names


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_trace_list(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    _, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "trace_list",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        for key in ds["trace"]:
            assert key in jres["result"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_valid(enqueue_job_mock, app):
    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    _, res_dict = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "valid",
                },
        headers={"Authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]
