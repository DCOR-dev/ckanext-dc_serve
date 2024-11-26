import logging
import pathlib
import tempfile
import traceback
import warnings

from ckan import common
import ckan.plugins.toolkit as toolkit
from dclab import RTDCWriter
from dclab.cli import condense_dataset
from dcor_shared import (
    DC_MIME_TYPES, get_dc_instance, s3cc, rqjob_register, s3, wait_for_resource
)
from dcor_shared import RQJob  # noqa: F401

import h5py

from .res_file_lock import CKANResourceFileLock


log = logging.getLogger(__name__)


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
        log.info("Generating condensed resources disabled via config")
        return False

    if not s3.is_available():
        log.info("S3 not available, not computing condensed resource")
        return False

    # make sure mimetype is defined
    if "mimetype" not in resource:
        suffix = "." + resource["name"].rsplit(".", 1)[-1]
        for mt in DC_MIME_TYPES:
            if suffix in DC_MIME_TYPES[mt]:
                resource["mimetype"] = mt
                break

    rid = resource["id"]
    log.info(f"Generating condensed resource {rid}")
    wait_for_resource(rid)
    if (resource.get('mimetype', '') in DC_MIME_TYPES
        # Check whether the file already exists on S3
        and (override
             or not s3cc.artifact_exists(resource_id=rid,
                                         artifact="condensed"))):
        # Create the condensed file in a cache location
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
                        feats_upstream = sorted(feats_src - feats_dst)

                    # Write DCOR basins
                    with RTDCWriter(path_cond) as hw:
                        # DCOR
                        site_url = common.config["ckan.site_url"]
                        rid = resource["id"]
                        dcor_url = f"{site_url}/api/3/action/dcserv?id={rid}"
                        hw.store_basin(
                            basin_name="DCOR dcserv",
                            basin_type="remote",
                            basin_format="dcor",
                            basin_locs=[dcor_url],
                            basin_descr="Original access via DCOR API",
                            basin_feats=feats_upstream,
                            verify=False)
                        # S3
                        s3_endpoint = common.config[
                            "dcor_object_store.endpoint_url"]
                        ds_dict = toolkit.get_action('package_show')(
                            admin_context(),
                            {'id': resource["package_id"]})
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
                            basin_feats=feats_upstream,
                            verify=False)
                        # HTTP (only works for public resources)
                        hw.store_basin(
                            basin_name="DCOR public S3 via HTTP",
                            basin_type="remote",
                            basin_format="http",
                            basin_locs=[s3_url],
                            basin_descr="Public resource access via HTTP",
                            basin_feats=feats_upstream,
                            verify=False)

                    # Upload the condensed file to S3
                    s3cc.upload_artifact(resource_id=rid,
                                         path_artifact=path_cond,
                                         artifact="condensed",
                                         override=True)
                    return True
        except BaseException:
            log.error(traceback.format_exc())
        finally:
            path_cond.unlink(missing_ok=True)
    return False
