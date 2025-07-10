import logging
import pathlib
import tempfile
import time
import traceback
import warnings

import botocore.exceptions
from ckan import common, model
import ckan.plugins.toolkit as toolkit
from dclab import RTDCWriter
from dclab.cli import condense_dataset
from dcor_shared import (
    DC_MIME_TYPES, get_dc_instance, s3cc, rqjob_register, s3, wait_for_resource
)
from dcor_shared import RQJob  # noqa: F401

import h5py

from .res_file_lock import CKANResourceFileLock


logger = logging.getLogger(__name__)


def admin_context():
    return {'ignore_auth': True, 'user': 'default'}


@rqjob_register(ckanext="dc_serve",
                queue="dcor-long",
                timeout=3600,
                )
def generate_condensed_resource(resource, override=False):
    """Condense .rtdc file and upload to S3"""
    # Check whether we should be generating a condensed resource file.
    if not common.asbool(common.config.get(
            "ckanext.dc_serve.create_condensed_datasets", "true")):
        logger.warning("Generating condensed resources disabled via config")
        return False

    if not s3.is_available():
        logger.error("S3 not available, not computing condensed resource")
        return False

    # make sure mimetype is defined
    if "mimetype" not in resource:
        suffix = "." + resource["name"].rsplit(".", 1)[-1]
        for mt in DC_MIME_TYPES:
            if suffix in DC_MIME_TYPES[mt]:
                resource["mimetype"] = mt
                break

    rid = resource["id"]
    wait_for_resource(rid)
    if (resource.get('mimetype', '') in DC_MIME_TYPES
        # Check whether the file already exists on S3
        and (override
             or not s3cc.artifact_exists(resource_id=rid,
                                         artifact="condensed"))):
        # Create the condensed file in a cache location
        logger.info(f"Generating condensed resource {rid}")
        cache_loc = common.config.get("ckanext.dc_serve.tmp_dir")
        if not cache_loc:
            cache_loc = None
        else:
            # Make sure the directory exists and don't panic when we cannot
            # create it.
            try:
                pathlib.Path(cache_loc).mkdir(parents=True, exist_ok=True)
            except BaseException:
                cache_loc = None

        if cache_loc is None:
            cache_loc = tempfile.mkdtemp(prefix="ckanext-dc_serve_")

        cache_loc = pathlib.Path(cache_loc)
        path_cond = cache_loc / f"{rid}_condensed.rtdc"

        try:
            with CKANResourceFileLock(
                    resource_id=rid,
                    locker_id="DCOR_generate_condensed") as fl:
                # The CKANResourceFileLock creates a lock file if not present
                # and then sets `is_locked` to True if the lock was acquired.
                # If the lock could not be acquired, that means that another
                # process is currently doing what we are attempting to do, so
                # we can just ignore this resource. The reason why I
                # implemented this is that I wanted to add an automated
                # background job for generating missing condensed files, but
                # then several processes would end up condensing the same
                # resource.
                if fl.is_locked:
                    _generate_condensed_resource(res_dict=resource,
                                                 path_cond=path_cond)
                    return True
        except BaseException:
            logger.error(traceback.format_exc())
        finally:
            path_cond.unlink(missing_ok=True)
    return False


def _generate_condensed_resource(res_dict, path_cond):
    """Condense dataset and add all relevant basins

    Creating the condensed resource (new file with scalar-only features)
    is only the first task of this function. The following basins are
    created as well:

    - "DCOR dcserv" basin (Original access via DCOR API):
      This basin can be accessed by every user with the necessary permissions.
    - "DCOR direct S3" basin (Direct access via S3):
      This basin can only be accessed with users that have S3 credentials
      set-up (this is not a normal use-case).
    - "DCOR public S3 via HTTP" basin (Public resource access via HTTP)
      This basin only works for public resources and facilitates fast
      resource access via HTTP.
    - "DCOR intra-dataset" basin (Upstream DCOR intra-dataset resource):
      If the original resource has a file-based basin that is part of the
      same DCOR dataset (must be uploaded beforehand), then this basin is
      a reference to it based on the DCOR API. The use case is data
      processed with dcnum when exploiting basins. Without this basin,
      image data would not be available when opening "_dcn.rtdc" files.
    """
    rid = res_dict["id"]
    # Now we would like to combine feature data
    with get_dc_instance(rid) as ds, \
            h5py.File(path_cond, "w") as h5_cond:
        # Features available in the input file
        feats_src = set(ds.features_innate)

        # Condense the dataset (do not store any warning
        # messages during instantiation, because we are
        # scared of leaking credentials).
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            condense_dataset(ds=ds,
                             h5_cond=h5_cond,
                             store_ancillary_features=True,
                             store_basin_features=True,
                             warnings_list=w)

        # Features available in the condensed file
        feats_dst = set(h5_cond["events"].keys())
        # Features that are in the input, but not in the
        # condensed file.
        feats_input = sorted(feats_src - feats_dst)
        if common.asbool(common.config.get(
                "ckanext.dc_serve.enable_intra_dataset_basins", "true")):
            # Additional upstream basins within this DCOR dataset.
            basins_upstream = _get_intra_dataset_upstream_basins(res_dict, ds)
        else:
            basins_upstream = []

    # Write DCOR basins
    with RTDCWriter(path_cond) as hw:
        # DCOR
        site_url = common.config["ckan.site_url"]
        rid = res_dict["id"]
        dcor_url = f"{site_url}/api/3/action/dcserv?id={rid}"
        hw.store_basin(
            basin_name="DCOR dcserv",
            basin_type="remote",
            basin_format="dcor",
            basin_locs=[dcor_url],
            basin_descr="Original access via DCOR API",
            basin_feats=feats_input,
            verify=False)
        # S3
        s3_endpoint = common.config[
            "dcor_object_store.endpoint_url"]
        ds_dict = toolkit.get_action('package_show')(
            admin_context(),
            {'id': res_dict["package_id"]})
        bucket_name = common.config[
            "dcor_object_store.bucket_name"].format(
            organization_id=ds_dict["organization"]["id"])
        obj_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
        s3_url = f"{s3_endpoint}/{bucket_name}/{obj_name}"
        hw.store_basin(
            basin_name="DCOR direct S3",
            basin_type="remote",
            basin_format="s3",
            basin_locs=[s3_url],
            basin_descr="Direct access via S3",
            basin_feats=feats_input,
            verify=False)
        # HTTP (only works for public resources)
        hw.store_basin(
            basin_name="DCOR public S3 via HTTP",
            basin_type="remote",
            basin_format="http",
            basin_locs=[s3_url],
            basin_descr="Public resource access via HTTP",
            basin_feats=feats_input,
            verify=False)

        # Additional upstream basins
        for bn_dict in basins_upstream:
            hw.store_basin(verify=False, **bn_dict)

    # Upload the condensed file to S3
    s3cc.upload_artifact(resource_id=rid,
                         path_artifact=path_cond,
                         artifact="condensed",
                         override=True)


def _get_intra_dataset_upstream_basins(res_dict, ds) -> list[dict]:
    """Search for intra-dataset resources and return corresponding basins"""
    site_url = common.config["ckan.site_url"]

    # Create a list of all resources in the dataset so far.
    pkg = model.Package.get(res_dict["package_id"])

    # Iterate through all basins in `ds` and create basin-create dictionaries.
    basin_dicts = []
    for bn_dict in ds.basins_get_dicts():
        if bn_dict["type"] == "file" and bn_dict["format"] == "hdf5":
            # Fetch the correct basin mapping feature data
            map_data = bn_dict.get("mapping", "same")
            if map_data == "same":
                basin_map = None
            else:
                basin_map = ds[map_data][:]

            # check whether the basin is in the list of resources.
            for res in pkg.resources:
                if _is_basin_of_dataset(ds, res, bn_dict):
                    # upstream resource ID
                    u_rid = res.id

                    # get the actual features available for this basin
                    ds_s3_res = s3cc.get_s3_dc_handle(u_rid, "resource")
                    basin_feats = _get_all_features_with_remote(ds_s3_res)
                    for ii in range(10):
                        # Workaround. I experienced AttributeErrors during
                        # testing ('S3File' object has no attribute 'seek'),
                        # possibly due to MinIO not having finalized the
                        # upload. In this case, simply try again.
                        try:
                            ds_s3_con = s3cc.get_s3_dc_handle(u_rid,
                                                              "condensed")
                        except AttributeError:
                            time.sleep(1)
                            logger.warning(
                                f"Workaround for attribute error, try: {ii}")
                            continue
                        except botocore.exceptions.ClientError:
                            # We are very likely self-referencing (404)
                            pass
                        except BaseException:
                            logger.warning(
                                f"Condensed resource {u_rid} not accessible, "
                                f"not extracting available features for "
                                f"intra-dataset basin; traceback follows.")
                            logger.warning(traceback.format_exc())
                        else:
                            con_f = _get_all_features_with_remote(ds_s3_con)
                            basin_feats = sorted(set(basin_feats + con_f))
                        break

                    # Add DCOR basin
                    u_dcor_url = f"{site_url}/api/3/action/dcserv?id={u_rid}"

                    if res_dict["id"] == u_rid:
                        # We are self.referencing
                        basin_name = f"DCOR self-reference {res.name}"
                        basin_descr = "Basin is the resource itself on DCOR"
                    else:
                        basin_name = f"DCOR intra-dataset for {res.name}"
                        basin_descr = "Upstream DCOR intra-dataset resource"

                    basin_dicts.append({
                        "basin_name": basin_name,
                        "basin_type": "remote",
                        "basin_format": "dcor",
                        "basin_locs": [u_dcor_url],
                        "basin_descr": basin_descr,
                        "basin_feats": basin_feats,
                        "basin_map": basin_map,
                    })

    return basin_dicts


def _get_all_features_with_remote(ds):
    """Return features, including remote features from basins"""
    features = ds.features
    for bn in ds.basins_get_dicts():
        if bn["type"] == "remote":
            features += bn["features"]
    return sorted(set(features))


def _is_basin_of_dataset(ds,
                         resource_basin,
                         basin_dict,
                         ):
    """Check whether a CKAN resource is a basin for a dataset

    Return True when `resource_basin` is a basin of `ds`
    as described by `basin_dict`.

    Parameters
    ----------
    ds:
        Instance of a dclab dataset
    resource_basin:
        CKAN resource object that is a potential basin for `ds`
    basin_dict:
        Corresponding basin dictionary to check against
    """
    # Open the potential basin and check its run identifier.
    ds_runid = ds.get_measurement_identifier()
    with get_dc_instance(resource_basin.id) as ds_bn:
        bn_runid = ds_bn.get_measurement_identifier()
    bn_runid_dict = basin_dict.get("identifier")

    if not bn_runid or not bn_runid_dict:
        # No run identifier specified -> no basin inference possible.
        return False

    if bn_runid != bn_runid_dict:
        # Basin-resource mismatch.
        # This resource is not the measurement referenced in this basin.
        return False

    mapping_is_same = basin_dict.get("mapping", "same") == "same"

    if mapping_is_same and bn_runid == ds_runid:
        # This is an ideal case. Both run identifiers match and the mapping
        # is identical.
        return True

    elif not mapping_is_same and ds_runid.startswith(bn_runid):
        # This is a slightly more complicated cases. If the mapping
        # is not "same", this means that we have filtered datasets.
        # For a filtered dataset, the identifier is the identifier of
        # its basin plus a unique string.
        return True

    # None of the above cases matched. This is not a direct basin of ds.
    return False
