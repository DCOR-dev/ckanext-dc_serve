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
def test_access_api_dcserv_error(app, create_with_upload):
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
    data = json.loads(resp.body)
    assert not data["success"]
    assert "Please specify 'query' parameter" in data["error"]["message"]

    # missing id parameter
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "feature",
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    data = json.loads(resp.body)
    assert not data["success"]
    assert "Please specify 'id' parameter" in data["error"]["message"]

    # bad ID
    bid = str(uuid.uuid4())
    resp = app.get(
        "/api/3/action/dcserv",
        params={"query": "feature",
                "id": bid,
                },
        headers={u"authorization": data["token"]},
        status=409
        )
    data = json.loads(resp.body)
    assert not data["success"]
    assert f"ID {bid} must be an .rtdc dataset!" in data["error"]["message"]


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_plugins', 'with_request_context')
def test_access_api_dcserv_feature(app, create_with_upload):
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
    data = json.loads(resp.body)
    assert data["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert np.allclose(ds["deform"], data["result"])
