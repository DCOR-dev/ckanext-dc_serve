"""Testing background jobs

Due to the asynchronous nature of background jobs, code that uses them needs
to be handled specially when writing tests.

A common approach is to use the mock package to replace the
ckan.plugins.toolkit.enqueue_job function with a mock that executes jobs
synchronously instead of asynchronously
"""
from unittest import mock
import pathlib

import pytest

import dclab
import numpy as np
import requests

from dcor_shared import s3cc
import dcor_shared


from dcor_shared.testing import make_dataset_via_s3, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_condensed_dataset_job_upload_s3(enqueue_job_mock, tmp_path):
    ds_dict, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    rid = res_dict["id"]

    # Sanity checks
    print("ACCESSING URL", res_dict["s3_url"])
    response = requests.get(res_dict["s3_url"])
    assert response.ok
    assert response.status_code == 200
    # Before attempting to access the object, make sure it was actually
    # created.
    assert s3cc.artifact_exists(rid, artifact="condensed")

    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url = f"{endpoint}/{bucket_name}/{object_name}"

    print("ACCESSING URL", cond_url)
    response = requests.get(cond_url)
    assert response.ok, "resource is public"
    assert response.status_code == 200

    # verify file validity
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    with dclab.new_dataset(dl_path) as ds:
        assert "volume" in ds
        assert np.allclose(ds["deform"][0], 0.011666297)


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.ckan_config('ckanext.dc_serve.create_condensed_datasets', "false")
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_do_not_create_condensed_by_config_dataset_job_upload_s3(
        enqueue_job_mock):
    ds_dict, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    rid = res_dict["id"]
    object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url = f"{endpoint}/{bucket_name}/{object_name}"
    response = requests.get(cond_url)
    assert not response.ok, "creating condensed resource should be disabled"


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dcor_schemas dc_serve')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_basin(
        enqueue_job_mock, tmp_path):
    ds_dict, res_dict = make_dataset_via_s3(
        resource_path=data_path / "calibration_beads_47.rtdc",
        activate=True)
    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    rid = res_dict["id"]
    object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url = f"{endpoint}/{bucket_name}/{object_name}"
    response = requests.get(cond_url)
    assert response.ok, "resource is public"
    assert response.status_code == 200

    # Download the condensed resource
    dl_path = tmp_path / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)

    # Open the condensed resource with dclab and make sure the
    # "image" feature is in the basin.
    with dclab.new_dataset(pathlib.Path(dl_path)) as ds:
        assert len(ds.basins) == 3
        assert "image" in ds.features
        assert "image" in ds.features_basin
        assert "image" not in ds.features_innate
        assert np.allclose(np.mean(ds["image"][0]),
                           47.15595,
                           rtol=0, atol=1e-4)
        # The basin features should only list those that are not in
        # the condensed dataset.
        assert ds.basins[0].features == [
            "contour", "image", "mask", "trace"]
