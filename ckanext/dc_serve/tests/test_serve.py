import json
import pathlib

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

    response = app.get(
        "/api/3/action/dcserv",
        params={"id": res["id"],
                "query": "feature",
                "feature": "deform",
                },
        headers={u"authorization": data["token"]},
        status=200
        )
    data = json.loads(response.body)
    assert data["success"]
    with dclab.new_dataset(data_path / "calibration_beads_47.rtdc") as ds:
        assert np.allclose(ds["deform"], data["result"])
