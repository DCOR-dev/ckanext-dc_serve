"""Testing background jobs

Due to the asynchronous nature of background jobs, code that uses them needs
to be handled specially when writing tests.

A common approach is to use the mock package to replace the
ckan.plugins.toolkit.enqueue_job function with a mock that executes jobs
synchronously instead of asynchronously
"""
import json
import pathlib
import shutil
from unittest import mock
import uuid

import pytest

from ckan import common
import ckan.tests.helpers as helpers
import dclab
import h5py
import numpy as np
import requests

from dcor_shared import s3cc
import dcor_shared


from dcor_shared.testing import (
    activate_dataset, make_dataset_via_s3, make_resource_via_s3,
    synchronous_enqueue_job
)


data_path = pathlib.Path(__file__).parent / "data"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_condensed_dataset_job_upload_s3(enqueue_job_mock, tmp_path):
    """Make sure condensed files are created and uploaded to S3"""
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


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.ckan_config('ckanext.dc_serve.create_condensed_datasets', "false")
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_do_not_create_condensed_by_config_dataset_job_upload_s3(
        enqueue_job_mock):
    """Make sure disabling `create_condensed_datasets` resources works"""
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


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_basin(
        enqueue_job_mock, tmp_path):
    """Make sure condensed resources can access original image feature"""
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


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
@pytest.mark.parametrize("filtered", [True, False])
def test_upload_condensed_dataset_to_s3_job_and_verify_intra_dataset_basin(
        enqueue_job_mock, tmp_path, filtered, app):
    """Make sure condensed resources can access intra-dataset features"""
    # generate a custom resource
    upstream_path = tmp_path / "upstream_data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", upstream_path)

    mid = str(uuid.uuid4())

    with h5py.File(upstream_path, "a") as hup:
        hup["events/userdef3"] = np.arange(len(hup["events/deform"]))
        hup.attrs["experiment:run identifier"] = mid
        # Remove the contour feature which is not well-supported when
        # subsetting basins.
        del hup["events/contour"]

    # Open the file in dclab, export a subset of deformation features
    downstream_path = tmp_path / "downstream_data.rtdc"
    with dclab.new_dataset(upstream_path) as ds:
        assert "userdef3" in ds
        ds.filter.manual[:] = False
        ds.filter.manual[2:10] = True
        ds.apply_filter()
        ds.export.hdf5(path=downstream_path,
                       features=["deform"],
                       filtered=filtered,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Make sure that worked
    with dclab.new_dataset(downstream_path) as ds:
        assert "userdef3" in ds.features_basin
        assert "userdef3" not in ds.features_innate
        if filtered:
            assert np.all(ds["userdef3"] == np.arange(2, 10))
        else:
            assert np.all(ds["userdef3"] == np.arange(47))

    # Create a draft dataset using the upstream dataset
    ds_dict, _ = make_dataset_via_s3(
        resource_path=upstream_path,
        private=False,
        activate=False)

    # Add the downstream resource to it
    rid = make_resource_via_s3(
        resource_path=downstream_path,
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )

    # activate the dataset
    activate_dataset(ds_dict["id"])

    # remove the local files
    upstream_path.unlink()
    downstream_path.unlink()

    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])

    object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url = f"{endpoint}/{bucket_name}/{object_name}"
    response = requests.get(cond_url)
    assert response.ok, "resource is public"
    assert response.status_code == 200

    print("Intra-dataset basins:",
          common.asbool(common.config.get(
              "ckanext.dc_serve.enable_intra_dataset_basins", "true"
          )))

    resp = app.get(
        "/api/3/action/dcserv",
        params={"id": rid,
                "query": "basins",
                },
        status=200
    )
    print("DCOR-BASINS", json.loads(resp.body))

    # Download the condensed resource
    dl_path = tmp_path / "downstream.rtdc"
    with dl_path.open("wb") as fd:
        fd.write(response.content)

    # Open the condensed resource with dclab and make sure the
    # "userdef3" feature is in the basins. When testing with docker,
    # the dcserv API is not accessible from within dclab, so we
    # only check the basin definitions.
    with dclab.new_dataset(pathlib.Path(dl_path)) as ds:
        basins = ds.basins_get_dicts()
        print("DOWNLOADED-BASINS", basins)
        for bn_dict in basins:
            if bn_dict["name"].count("DCOR intra-dataset"):
                assert "userdef3" in bn_dict["features"]
                break
        else:
            assert False, "no intra-dataset basin"

        assert "userdef3" not in ds.features_innate


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_intra_dataset_basin_ren(
        enqueue_job_mock, tmp_path):
    """Make sure condensed resources can access intra-dataset features

    This test tests against renamed resources. Here, the job must identify
    upstream basins based on run identifiers.
    """
    # generate a custom resource
    upstream_path = tmp_path / "upstream_data.rtdc"
    midstream_path = tmp_path / "midstream_data.rtdc"
    downstream_path = tmp_path / "downstream_data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", upstream_path)

    mid = str(uuid.uuid4())

    with h5py.File(upstream_path, "a") as hup:
        hup["events/userdef3"] = np.arange(len(hup["events/deform"]))
        hup.attrs["experiment:run identifier"] = mid
        # Remove the contour feature which is not well-supported when
        # subsetting basins.
        del hup["events/contour"]

    # Add a link in-between that only exports a few features.
    with dclab.new_dataset(upstream_path) as ds:
        ds.export.hdf5(path=midstream_path,
                       features=["deform", "area_um"],
                       filtered=False,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Open the file in dclab, export a subset of deformation features
    with dclab.new_dataset(midstream_path) as ds:
        assert "userdef3" in ds
        ds.filter.manual[:] = False
        ds.filter.manual[2:10] = True
        ds.apply_filter()
        ds.export.hdf5(path=downstream_path,
                       features=["deform"],
                       filtered=True,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Make sure that worked
    with dclab.new_dataset(downstream_path) as ds:
        assert "userdef3" in ds.features_basin
        assert "userdef3" not in ds.features_innate
        assert np.all(ds["userdef3"] == np.arange(2, 10))

    # Create a draft dataset using the upstream dataset
    ds_dict = make_dataset_via_s3(
        private=False,
        activate=False)

    # Add all resource
    rid1 = make_resource_via_s3(
        resource_path=upstream_path,
        resource_name="anakin.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    rid2 = make_resource_via_s3(
        resource_path=midstream_path,
        resource_name="luke.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    rid3 = make_resource_via_s3(
        resource_path=downstream_path,
        resource_name="rey.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    # activate the dataset
    activate_dataset(ds_dict["id"])

    # remove the local files
    downstream_path.unlink()
    midstream_path.unlink()
    upstream_path.unlink()

    ds_dict = helpers.call_action("package_show", id=ds_dict["id"])
    res_names = [r["name"] for r in ds_dict["resources"]]
    assert res_names == ["anakin.rtdc", "luke.rtdc", "rey.rtdc"]

    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])

    object_name_1 = f"condensed/{rid1[:3]}/{rid1[3:6]}/{rid1[6:]}"
    object_name_2 = f"condensed/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    object_name_3 = f"condensed/{rid3[:3]}/{rid3[3:6]}/{rid3[6:]}"

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url_2 = f"{endpoint}/{bucket_name}/{object_name_2}"
    cond_url_3 = f"{endpoint}/{bucket_name}/{object_name_3}"

    for obj in [object_name_1, object_name_2, object_name_3]:
        cond_url = f"{endpoint}/{bucket_name}/{obj}"
        response = requests.get(cond_url)
        assert response.ok, "resource is public"
        assert response.status_code == 200

    # Download the condensed resource2
    response_2 = requests.get(cond_url_2)
    dl_path_2 = tmp_path / "middle.rtdc"
    with dl_path_2.open("wb") as fd:
        fd.write(response_2.content)

    # Open the condensed resource with dclab and make sure the
    # "userdef3" feature is in the basins. When testing with docker,
    # the dcserv API is not accessible from within dclab, so we
    # only check the basin definitions.

    # This is the non-filtered dataset
    with dclab.new_dataset(pathlib.Path(dl_path_2)) as ds:
        assert "area_um" in ds.features_innate
        assert "userdef3" not in ds.features_innate
        basins = ds.basins_get_dicts()
        print("BASINS2", basins)
        for bn_dict in basins:
            if bn_dict["name"].count("DCOR intra-dataset"):
                assert bn_dict["mapping"] == "same"
                assert "userdef3" in bn_dict["features"]
                break
        else:
            assert False, "no intra-dataset basin"

    # Download the condensed resource3
    response_3 = requests.get(cond_url_3)
    dl_path_3 = tmp_path / "down.rtdc"
    with dl_path_3.open("wb") as fd:
        fd.write(response_3.content)

    # This is the subsetted dataset.
    with dclab.new_dataset(pathlib.Path(dl_path_3)) as ds:
        assert "area_um" not in ds.features_innate
        assert "userdef3" not in ds.features_innate
        basins = ds.basins_get_dicts()
        print("BASINS3", basins)
        for bn_dict in basins:
            if bn_dict["name"].count("DCOR intra-dataset for anakin.rtdc"):
                assert bn_dict["mapping"] == "basinmap0"
                assert "userdef3" in bn_dict["features"]
                break
        else:
            assert False, "no intra-dataset basin"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_intra_dataset_basin_chn(
        enqueue_job_mock, tmp_path):
    """Chain of non-"same" basins.

    This test tests against renamed resources. Here, the job must identify
    upstream basins based on run identifiers.
    """
    # generate a custom resource
    upstream_path = tmp_path / "upstream_data.rtdc"
    midstream_path = tmp_path / "midstream_data.rtdc"
    downstream_path = tmp_path / "downstream_data.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", upstream_path)

    mid = str(uuid.uuid4())

    with h5py.File(upstream_path, "a") as hup:
        hup["events/userdef3"] = np.arange(len(hup["events/deform"]))
        hup.attrs["experiment:run identifier"] = mid
        # Remove the contour feature which is not well-supported when
        # subsetting basins.
        del hup["events/contour"]

    # Add a link in-between that only exports a few features.
    with dclab.new_dataset(upstream_path) as ds:
        ds.filter.manual[:] = True
        ds.filter.manual[:2] = False
        ds.apply_filter()
        ds.export.hdf5(path=midstream_path,
                       features=["deform", "area_um"],
                       filtered=True,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Open the file in dclab, export a subset of deformation features
    with dclab.new_dataset(midstream_path) as ds:
        assert "userdef3" in ds
        ds.filter.manual[:] = False
        ds.filter.manual[2:10] = True
        ds.apply_filter()
        ds.export.hdf5(path=downstream_path,
                       features=["deform"],
                       filtered=True,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Make sure that worked
    with dclab.new_dataset(downstream_path) as ds:
        assert "userdef3" in ds.features_basin
        assert "userdef3" not in ds.features_innate
        assert np.all(ds["userdef3"] == np.arange(4, 12))

    # Create a draft dataset using the upstream dataset
    ds_dict = make_dataset_via_s3(
        private=False,
        activate=False)

    # Add all resource
    rid1 = make_resource_via_s3(
        resource_path=upstream_path,
        resource_name="anakin.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    rid2 = make_resource_via_s3(
        resource_path=midstream_path,
        resource_name="luke.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    rid3 = make_resource_via_s3(
        resource_path=downstream_path,
        resource_name="rey.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    # activate the dataset
    activate_dataset(ds_dict["id"])

    # remove the local files
    downstream_path.unlink()
    midstream_path.unlink()
    upstream_path.unlink()

    ds_dict = helpers.call_action("package_show", id=ds_dict["id"])
    res_names = [r["name"] for r in ds_dict["resources"]]
    assert res_names == ["anakin.rtdc", "luke.rtdc", "rey.rtdc"]

    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])

    object_name_1 = f"condensed/{rid1[:3]}/{rid1[3:6]}/{rid1[6:]}"
    object_name_2 = f"condensed/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    object_name_3 = f"condensed/{rid3[:3]}/{rid3[3:6]}/{rid3[6:]}"

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url_2 = f"{endpoint}/{bucket_name}/{object_name_2}"
    cond_url_3 = f"{endpoint}/{bucket_name}/{object_name_3}"

    for obj in [object_name_1, object_name_2, object_name_3]:
        cond_url = f"{endpoint}/{bucket_name}/{obj}"
        response = requests.get(cond_url)
        assert response.ok, "resource is public"
        assert response.status_code == 200

    # Download the condensed resource2
    response_2 = requests.get(cond_url_2)
    dl_path_2 = tmp_path / "middle.rtdc"
    with dl_path_2.open("wb") as fd:
        fd.write(response_2.content)

    # Open the condensed resource with dclab and make sure the
    # "userdef3" feature is in the basins. When testing with docker,
    # the dcserv API is not accessible from within dclab, so we
    # only check the basin definitions.

    # This is the non-filtered dataset
    with dclab.new_dataset(pathlib.Path(dl_path_2)) as ds:
        assert "area_um" in ds.features_innate
        assert "userdef3" not in ds.features_innate
        basins = ds.basins_get_dicts()
        print("BASINS2", basins)
        print("RUNID2", ds.get_measurement_identifier())

        for bn_dict in basins:
            if bn_dict["name"].count("DCOR intra-dataset for anakin.rtdc"):
                assert bn_dict["mapping"] == "basinmap0"
                assert "userdef3" in bn_dict["features"]
                break
        else:
            assert False, "no intra-dataset basin"

    # Download the condensed resource3
    response_3 = requests.get(cond_url_3)
    dl_path_3 = tmp_path / "down.rtdc"
    with dl_path_3.open("wb") as fd:
        fd.write(response_3.content)

    # This is the subsetted dataset.
    with dclab.new_dataset(pathlib.Path(dl_path_3)) as ds:
        assert "area_um" not in ds.features_innate
        assert "userdef3" not in ds.features_innate
        basins = ds.basins_get_dicts()
        print("BASINS3", basins)
        print("RUNID3", ds.get_measurement_identifier())
        for bn_dict in basins:
            if bn_dict["name"].count("DCOR intra-dataset for luke.rtdc"):
                assert bn_dict["mapping"] == "basinmap1"
                assert "userdef3" in bn_dict["features"]
                break
        else:
            assert False, "no intra-dataset basin"


@pytest.mark.ckan_config('ckan.plugins', 'dcor_schemas dc_serve')
@pytest.mark.usefixtures('with_plugins', 'clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_upload_condensed_dataset_to_s3_job_and_verify_intra_dataset_basin_ctl(
        enqueue_job_mock, tmp_path):
    """Make sure resources don't get assigned incorrectly as basins"""
    # generate a custom resource
    upstream_path = tmp_path / "upstream_data.rtdc"
    downstream_path1 = tmp_path / "downstream_data_1.rtdc"
    downstream_path2 = tmp_path / "downstream_data_2.rtdc"
    shutil.copy2(data_path / "calibration_beads_47.rtdc", upstream_path)

    mid = str(uuid.uuid4())

    with h5py.File(upstream_path, "a") as hup:
        hup["events/userdef3"] = np.arange(len(hup["events/deform"]))
        hup.attrs["experiment:run identifier"] = mid
        # Remove the contour feature which is not well-supported when
        # subsetting basins.
        del hup["events/contour"]

    # Open the file in dclab, export a subset of deformation features
    with dclab.new_dataset(upstream_path) as ds:
        assert "userdef3" in ds
        ds.filter.manual[:] = False
        ds.filter.manual[2:10] = True
        ds.apply_filter()
        ds.export.hdf5(path=downstream_path1,
                       features=["deform", "area_um", "userdef3"],
                       filtered=True,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

        ds.filter.manual[:] = False
        ds.filter.manual[3:10] = True
        ds.apply_filter()
        ds.export.hdf5(path=downstream_path2,
                       features=["deform"],
                       filtered=True,
                       logs=True,
                       tables=True,
                       basins=True,
                       )

    # Create a draft dataset using the upstream dataset
    ds_dict = make_dataset_via_s3(
        private=False,
        activate=False)

    # Add all resource
    rid2 = make_resource_via_s3(
        resource_path=downstream_path1,
        resource_name="luke.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    rid3 = make_resource_via_s3(
        resource_path=downstream_path2,
        resource_name="rey.rtdc",
        organization_id=ds_dict["organization"]["id"],
        dataset_id=ds_dict["id"],
        private=False,
    )
    # activate the dataset
    activate_dataset(ds_dict["id"])

    # remove the local files
    upstream_path.unlink()
    downstream_path1.unlink()
    downstream_path2.unlink()

    ds_dict = helpers.call_action("package_show", id=ds_dict["id"])
    res_names = [r["name"] for r in ds_dict["resources"]]
    assert res_names == ["luke.rtdc", "rey.rtdc"]

    bucket_name = dcor_shared.get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])

    object_name_2 = f"condensed/{rid2[:3]}/{rid2[3:6]}/{rid2[6:]}"
    object_name_3 = f"condensed/{rid3[:3]}/{rid3[3:6]}/{rid3[6:]}"

    endpoint = dcor_shared.get_ckan_config_option(
        "dcor_object_store.endpoint_url")
    cond_url_2 = f"{endpoint}/{bucket_name}/{object_name_2}"
    cond_url_3 = f"{endpoint}/{bucket_name}/{object_name_3}"

    for obj in [object_name_2, object_name_3]:
        cond_url = f"{endpoint}/{bucket_name}/{obj}"
        response = requests.get(cond_url)
        assert response.ok, "resource is public"
        assert response.status_code == 200

    # Download the condensed resource2
    response_2 = requests.get(cond_url_2)
    dl_path_2 = tmp_path / "middle.rtdc"
    with dl_path_2.open("wb") as fd:
        fd.write(response_2.content)

    # This is  the non-filtered dataset
    with dclab.new_dataset(pathlib.Path(dl_path_2)) as ds:
        assert "deform" in ds.features_innate
        assert "userdef3" in ds.features_innate

    # Download the condensed resource3
    response_3 = requests.get(cond_url_3)
    dl_path_3 = tmp_path / "down.rtdc"
    with dl_path_3.open("wb") as fd:
        fd.write(response_3.content)

    # This is the subsetted dataset.
    with dclab.new_dataset(pathlib.Path(dl_path_3)) as ds:
        assert "deform" in ds.features_innate
        # check for false basin assignment
        assert "area_um" not in ds.features
        assert "userdef3" not in ds.features
