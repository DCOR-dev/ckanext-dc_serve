import pathlib
from unittest import mock

import ckanext.dcor_schemas.plugin
import ckanext.dc_serve.helpers as serve_helpers

from dcor_shared import get_resource_path

import pytest
import ckan.tests.factories as factories
from dcor_shared.testing import make_dataset, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_file(enqueue_job_mock, create_with_upload,
                              monkeypatch):
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    ds_dict, _ = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    rid = ds_dict["resources"][0]["id"]
    resource_path = pathlib.Path(get_resource_path(rid))
    assert resource_path.exists(), "sanity check"
    assert serve_helpers.resource_has_condensed(rid)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_get_dc_instance_s3(enqueue_job_mock, create_with_upload,
                            monkeypatch):
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    create_context = {'ignore_auth': False,
                      'user': user['name'],
                      'api_version': 3}
    ds_dict, _ = make_dataset(
        create_context, owner_org,
        create_with_upload=create_with_upload,
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    res_dict = ds_dict["resources"][0]
    rid = res_dict["id"]
    resource_path = pathlib.Path(get_resource_path(rid))
    # remove the file, so DCOR falls back to the S3 resource
    resource_path.unlink()
    assert not resource_path.exists(), "sanity check"
    assert serve_helpers.resource_has_condensed(rid)
