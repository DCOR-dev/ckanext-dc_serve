import copy
import json
import mock
import shutil
import uuid

import ckan.model as model
import ckan.common
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
import ckanext.dcor_schemas
import dclab
import h5py
import numpy as np

import pytest

from .helper_methods import data_path, make_dataset, synchronous_enqueue_job


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_auth_forbidden(app, create_with_upload):
    user = factories.User()
    user2 = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True,
                                private=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data2 = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user2[u"name"]},
        user=user2[u"name"],
        name=u"token-name",
    )
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "valid",
                },
        headers={u"authorization": data2["token"]},
        status=403
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "not authorized to read resource" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_error(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    # missing query parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                },
        headers={u"authorization": data["token"]},
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
        headers={u"authorization": data["token"]},
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
        headers={u"authorization": data["token"]},
        status=404
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Not found" in jres["error"]["message"]

    # invalid query
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "peter",
                "id": res["id"],
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Invalid query parameter 'peter'" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_error_feature(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    # missing feature parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'feature' parameter" in jres["error"]["message"]

    # missing event parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "image",
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'event' for non-scalar" in jres["error"]["message"]

    # bad feature name
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "peter",
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Unknown feature name 'peter'" in jres["error"]["message"]

    # feature unavailable
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "ml_score_xyz",
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Feature 'ml_score_xyz' unavailable" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_error_feature_trace(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    # missing trace parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "trace",
                "event": 2,
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "Please specify 'trace' parameter" in jres["error"]["message"]

    # missing event parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "trace",
                "trace": "fl1_raw"
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    jres = json.loads(resp.body)
    assert not jres["success"]
    assert "lease specify 'event' for non-scalar" in jres["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_basin(app, create_with_upload):
    user = factories.User()
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
    path_test = data_path / "calibration_beads_47_test.rtdc"
    shutil.copy2(path_orig, path_test)
    with dclab.RTDCWriter(path_test) as hw:
        hw.store_basin(basin_name="example basin",
                       basin_type="file",
                       basin_format="hdf5",
                       basin_locs=[path_orig],
                       basin_descr="an example test basin",
                       )

    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                test_file_name=path_test.name,
                                activate=True)

    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "basins",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    basin = jres["result"][0]
    assert basin["name"] == "example basin"
    assert basin["type"] == "file"
    assert basin["format"] == "hdf5"
    assert basin["description"] == "an example test basin"


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

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    user_obj = ckan.model.User.by_name(user["name"])
    monkeypatch.setattr(ckan.common,
                        'current_user',
                        user_obj)
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}

    dataset, res = make_dataset(copy.deepcopy(create_context), owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)

    s3_url = res["s3_url"]

    # create a dataset
    path_orig = data_path / "calibration_beads_47.rtdc"
    path_test = data_path / "calibration_beads_47_test.rtdc"
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
                       verify=False,  # we don't have s3fs installed
                       )
        del hw.h5file["events/deform"]

    with h5py.File(path_test) as h5:
        # sanity check
        assert "deform" not in h5["events"]

    dataset, res = make_dataset(copy.deepcopy(create_context), owner_org,
                                create_with_upload=create_with_upload,
                                test_file_name=path_test.name,
                                activate=True)

    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    # Version 1 API does serve all features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature_list",
                "version": "1",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 37

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature_list",
                "version": "2",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert len(jres["result"]) == 0

    # Version 2 API does not serve any features
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "area_um",
                "version": "2",
                },
        headers={u"authorization": data["token"]},
        status=409  # ValidationError
        )
    jres = json.loads(resp.body)
    assert not jres["success"]

    # Version two API serves basins
    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "basins",
                "version": "2",
                },
        headers={u"authorization": data["token"]},
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
        assert bn["format"] == "s3"
        assert bn["name"] in ["condensed", "resource"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_feature(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "deform",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert np.allclose(ds["deform"], jres["result"])


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_feature_list(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature_list",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert "deform" in jres["result"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_feature_trace(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "trace",
                "trace": "fl1_raw",
                "event": 1,
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert np.allclose(ds["trace"]["fl1_raw"][1], jres["result"])


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_logs(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "logs",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["hans"][0] == "peter"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_metadata(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "metadata",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]["setup"]["channel width"] == 20


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_size(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "size",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert jres["result"] == len(ds)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_tables(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                test_file_name="cytoshot_blood.rtdc",
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "tables",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert "src_cytoshot_monitor" in jres["result"]
    names, data = jres["result"]["src_cytoshot_monitor"]
    assert "brightness" in names


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_trace_list(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "trace_list",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        for key in ds["trace"]:
            assert key in jres["result"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
def test_api_dcserv_valid(app, create_with_upload):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    create_context = {'ignore_auth': False,
                      'user': user['name'], 'api_version': 3}
    # create a dataset
    dataset, res = make_dataset(create_context, owner_org,
                                create_with_upload=create_with_upload,
                                activate=True)
    # taken from ckanext/example_iapitoken/tests/test_plugin.py
    data = helpers.call_action(
        u"api_token_create",
        context={u"model": model, u"user": user[u"name"]},
        user=user[u"name"],
        name=u"token-name",
    )

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "valid",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    jres = json.loads(resp.body)
    assert jres["success"]
    assert jres["result"]
