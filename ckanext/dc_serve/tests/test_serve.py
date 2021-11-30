import json
import pathlib
import uuid

import ckan.model as model
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
import dclab
import numpy as np

import pytest

from .helper_methods import make_dataset


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
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
