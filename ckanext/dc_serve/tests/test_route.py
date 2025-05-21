import pathlib
from unittest import mock

import ckan.tests.factories as factories
import dcor_shared
from dcor_shared import s3cc

import pytest

from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
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

    # sanity check
    assert s3cc.artifact_exists(rid, artifact="resource")
    assert s3cc.artifact_exists(rid, artifact="condensed")

    did = ds_dict["id"]
    # We should not be authorized to access the resource without API token
    resp0 = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
        status=404
    )
    assert len(resp0.history) == 0

    resp = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
        headers={"Authorization": user["token"]},
        follow_redirects=False,
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp
    assert resp.status_code == 302
    redirect_stem = (f"{endpoint}/{bucket_name}/condensed/"
                     f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")
    # Since we have a presigned URL, it is longer than the normal S3 URL.
    assert redirect.location.startswith(redirect_stem)
    assert len(redirect.location) > len(redirect_stem)


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
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

    did = ds_dict["id"]
    resp = app.get(
        f"/dataset/{did}/resource/{rid}/condensed.rtdc",
        follow_redirects=False,
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp
    assert redirect.status_code == 302
    assert redirect.location.startswith(f"{endpoint}/{bucket_name}/condensed/"
                                        f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db')
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

    did = ds_dict["id"]
    # We should not be authorized to access the resource without API token
    app.get(
        f"/dataset/{did}/resource/{rid}/download/calibration_beads_47.rtdc",
        status=404
    )

    resp = app.get(
        f"/dataset/{did}/resource/{rid}/download/calibration_beads_47.rtdc",
        headers={"Authorization": user["token"]},
        follow_redirects=False,
    )

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    redirect = resp
    assert redirect.status_code == 302
    redirect_stem = (f"{endpoint}/{bucket_name}/resource/"
                     f"{rid[:3]}/{rid[3:6]}/{rid[6:]}")
    # Since we have a presigned URL, it is longer than the normal S3 URL.
    assert redirect.location.startswith(redirect_stem)
    assert len(redirect.location) > len(redirect_stem)
