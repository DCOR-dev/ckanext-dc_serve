import copy
import json
import pathlib
from unittest import mock
import shutil
import uuid

import ckan.common
import ckan.tests.factories as factories
import ckanext.dcor_schemas
import dclab
from dclab.rtdc_dataset import fmt_http
import h5py

import pytest

from dcor_shared.testing import make_dataset, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_auth_forbidden(app, create_with_upload):
    user2 = factories.UserWithToken()

    # create a dataset
    _, res_dict = make_dataset(
        create_with_upload=create_with_upload,
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
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_error(app, create_with_upload):
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
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    # missing query parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                },
        headers={u"authorization": user["token"]},
        status=409
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'query' parameter" in jres["error"]["message"]

    # missing id parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "feature",
                },
        headers={u"authorization": user["token"]},
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
        headers={u"authorization": user["token"]},
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
        headers={u"authorization": user["token"]},
        status=409
    )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Invalid query parameter 'peter'" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin(enqueue_job_mock, app, create_with_upload,
                          monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)
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
    path_test = pathlib.Path(tmpdir) / "calibration_beads_47_test.rtdc"
    shutil.copy2(path_orig, path_test)
    with dclab.RTDCWriter(path_test) as hw:
        hw.store_basin(basin_name="example basin",
                       basin_type="remote",
                       basin_format="http",
                       basin_locs=["http://example.org/peter/pan.rtdc"],
                       basin_descr="an example test basin",
                       verify=False,  # does not exist
                       )

    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=path_test,
        activate=True,
        private=False,
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "basins",
                },
        headers={u"authorization": user["token"]},
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


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_basin_v2(enqueue_job_mock, app, create_with_upload,
                             monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    user_obj = ckan.model.User.by_name(user["name"])
    monkeypatch.setattr(ckan.common,
                        'current_user',
                        user_obj)
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    _, res_dict = make_dataset(
        copy.deepcopy(create_context),
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    s3_url = res_dict["s3_url"]

    # create a dataset
    path_orig = data_path / "calibration_beads_47.rtdc"
    path_test = pathlib.Path(tmpdir) / "calibration_beads_47_test.rtdc"
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

    ds_dict, res_dict = make_dataset(
        copy.deepcopy(create_context),
        create_with_upload=create_with_upload,
        resource_path=path_test,
        activate=True)

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "feature_list",
                "version": "2",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 0

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "feature",
                "feature": "area_um",
                "version": "2",
                },
        headers={u"authorization": user["token"]},
        status=409  # ValidationError
    )
    jres = json.loads(resp.body)
    assert not jres["success"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "basins",
                "version": "2",
                },
        headers={u"authorization": user["token"]},
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
        assert bn["name"] in ["condensed", "resource"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_feature_list(enqueue_job_mock, app, ckan_config,
                                 create_with_upload, monkeypatch, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "feature_list",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 0, "deprecated"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_logs(enqueue_job_mock, app, ckan_config,
                         create_with_upload, monkeypatch, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "logs",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["hans"][0] == "peter"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_metadata(enqueue_job_mock, app, create_with_upload,
                             monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

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
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "metadata",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["setup"]["channel width"] == 20


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_size(enqueue_job_mock, app, create_with_upload,
                         monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "size",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert jres["result"] == len(ds)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_tables(enqueue_job_mock, app, create_with_upload,
                           monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    ds_dict, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "cytoshot_blood.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "tables",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert "src_cytoshot_monitor" in jres["result"]
    names, data = jres["result"]["src_cytoshot_monitor"]
    assert "brightness" in names


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_trace_list(enqueue_job_mock, app, create_with_upload,
                               monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    _, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "trace_list",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        for key in ds["trace"]:
            assert key in jres["result"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_api_dcserv_valid(enqueue_job_mock, app, create_with_upload,
                          monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.UserWithToken()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    _, res_dict = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res_dict["id"],
                "query": "valid",
                },
        headers={u"authorization": user["token"]},
        status=200
    )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]
