import pathlib
from unittest import mock

import ckanext.dc_serve.helpers as serve_helpers

import pytest
import ckan.tests.factories as factories
from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_s3(enqueue_job_mock):
    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    ds_dict, _ = make_dataset_via_s3(
        create_context=create_context,
        owner_org=owner_org,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    res_dict = ds_dict["resources"][0]
    rid = res_dict["id"]

    assert serve_helpers.resource_has_condensed(rid)
