import pathlib
from unittest import mock

import ckan.tests.factories as factories
import dcor_shared

import pytest

from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_route_redircet_condensed_to_s3_private(enqueue_job_mock, app):
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
        activate=True,
        private=True
    )
    rid = res_dict["id"]
    assert "s3_available" in res_dict
    assert "s3_url" in res_dict

    # Since version 0.15.0 we don't store the condensed resource locally
    path = dcor_shared.get_resource_path(rid)
    path_cond = path.with_name(path.name + "_condensed.rtdc")
    assert not path_cond.exists(), "sanity check"

    did = ds_dict["id"]
    # We should not be authorized to access the resource without API token
    resp0 = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
        status=404
    )
    assert len(resp0.history) == 0

    resp = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
        headers={u"authorization": user["token"]},
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp.history[0]
    assert redirect.status_code == 302
    redirect_stem = (f"{endpoint}/{bucket_name}/condensed/"
                     f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")
    # Since we have a presigned URL, it is longer than the normal S3 URL.
    assert redirect.location.startswith(redirect_stem)
    assert len(redirect.location) > len(redirect_stem)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_route_condensed_to_s3_public(enqueue_job_mock, app):
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
    rid = res_dict["id"]
    assert "s3_available" in res_dict
    assert "s3_url" in res_dict

    # Since version 0.15.0 we don't store the condensed resource locally
    path = dcor_shared.get_resource_path(rid)
    path_cond = path.with_name(path.name + "_condensed.rtdc")
    assert not path_cond.exists(), "sanity check"

    did = ds_dict["id"]
    resp = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp.history[0]
    assert redirect.status_code == 302
    assert redirect.location.startswith(f"{endpoint}/{bucket_name}/condensed/"
                                        f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")


@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_route_redircet_resource_to_s3_private(enqueue_job_mock, app):
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
        activate=True,
        private=True
    )
    rid = res_dict["id"]
    assert "s3_available" in res_dict
    assert "s3_url" in res_dict

    # Since version 0.15.0 we don't store the condensed resource locally
    path = dcor_shared.get_resource_path(rid)
    path_cond = path.with_name(path.name + "_condensed.rtdc")
    assert not path_cond.exists(), "sanity check"

    did = ds_dict["id"]
    # We should not be authorized to access the resource without API token
    resp0 = app.get(
        f"/dataset/{did}/resource/{rid}/download/random_name",
        status=404
    )
    assert len(resp0.history) == 0

    resp = app.get(
        f"/dataset/{did}/resource/{rid}/download/random_name",
        headers={u"authorization": user["token"]},
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp.history[0]
    assert redirect.status_code == 302
    redirect_stem = (f"{endpoint}/{bucket_name}/resource/"
                     f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")
    # Since we have a presigned URL, it is longer than the normal S3 URL.
    assert redirect.location.startswith(redirect_stem)
    assert len(redirect.location) > len(redirect_stem)
