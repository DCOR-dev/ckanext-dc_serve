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

import ckan.lib
import dclab
import numpy as np
import requests

import ckanext.dcor_schemas.plugin
import dcor_shared


from dcor_shared.testing import make_dataset, synchronous_enqueue_job


data_path = pathlib.Path(__file__).parent / "data"


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dc_serve dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_condensed_dataset_job_upload_s3(
        enqueue_job_mock, create_with_upload, monkeypatch, ckan_config,
        tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    ds_dict, res_dict = make_dataset(
        create_with_upload=create_with_upload,
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

    # verify file validity
    dl_path = pathlib.Path(tmpdir) / "calbeads.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)
    with dclab.new_dataset(dl_path) as ds:
        assert "volume" in ds
        assert np.allclose(ds["deform"][0], 0.011666297)

    # the local file path should not exist anymore since version 0.15.0
    path = dcor_shared.get_resource_path(res_dict["id"])
    path_cond = path.with_name(path.name + "_condensed.rtdc")
    assert not path_cond.exists()


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dc_serve dcor_schemas')
@pytest.mark.ckan_config('ckanext.dc_serve.create_condensed_datasets', "false")
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_do_not_create_condensed_by_config_dataset_job_upload_s3(
        enqueue_job_mock, create_with_upload, monkeypatch, ckan_config,
        tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    ds_dict, res_dict = make_dataset(
        create_with_upload=create_with_upload,
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
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dc_serve dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_basin(
        enqueue_job_mock, create_with_upload, monkeypatch, ckan_config,
        tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader,
                        'get_storage_path',
                        lambda: str(tmpdir))
    monkeypatch.setattr(
        ckanext.dcor_schemas.plugin,
        'DISABLE_AFTER_DATASET_CREATE_FOR_CONCURRENT_JOB_TESTS',
        True)

    ds_dict, res_dict = make_dataset(
        create_with_upload=create_with_upload,
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
    dl_path = pathlib.Path(tmpdir) / "calbeads.rtdc"
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
