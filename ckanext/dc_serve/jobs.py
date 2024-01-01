import ckan.plugins.toolkit as toolkit
from dclab import RTDCWriter
from dclab.cli import condense
from dcor_shared import (
    DC_MIME_TYPES, s3, sha256sum, get_ckan_config_option, get_resource_path,
    wait_for_resource)
import h5py

from .res_file_lock import CKANResourceFileLock


def admin_context():
    return {'ignore_auth': True, 'user': 'default'}


def generate_condensed_resource_job(resource, override=False):
    """Generates a condensed version of the dataset"""
    path = get_resource_path(resource["id"])
    if resource["mimetype"] in DC_MIME_TYPES:
        wait_for_resource(path)
        cond = path.with_name(path.name + "_condensed.rtdc")
        if not cond.exists() or override:
            with CKANResourceFileLock(
                    resource_id=resource["id"],
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
                    # Condense the dataset
                    condense(path_out=cond,
                             path_in=path,
                             ancillaries=True,
                             check_suffix=False)
                    # Determine the features that are not in the condensed
                    # dataset.
                    with h5py.File(path) as hsrc, h5py.File(cond) as hdst:
                        feats_src = set(hsrc["events"].keys())
                        feats_dst = set(hdst["events"].keys())
                    feats_upstream = sorted(feats_src - feats_dst)

                    # Write DCOR basins
                    with RTDCWriter(cond) as hw:
                        # DCOR
                        site_url = get_ckan_config_option("ckan.site_url")
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
                        s3_endpoint = get_ckan_config_option(
                            "dcor_object_store.endpoint_url")
                        ds_dict = toolkit.get_action('package_show')(
                            admin_context(),
                            {'id': resource["package_id"]})
                        bucket_name = get_ckan_config_option(
                            "dcor_object_store.bucket_name").format(
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
                    return True
    return False


def migrate_condensed_to_s3_job(resource):
    """Migrate a condensed resource to the S3 object store"""
    path = get_resource_path(resource["id"])
    path_cond = path.with_name(path.name + "_condensed.rtdc")
    ds_dict = toolkit.get_action('package_show')(
        admin_context(),
        {'id': resource["package_id"]})
    # Perform the upload
    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    rid = resource["id"]
    sha256 = sha256sum(path_cond)
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}",
        path=path_cond,
        sha256=sha256,
        private=ds_dict["private"])
    # TODO: delete the local resource after successful upload?
