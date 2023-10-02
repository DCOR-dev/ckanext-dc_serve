import multiprocessing

import ckan.plugins.toolkit as toolkit
from dclab.cli import condense
from dcor_shared import (
    DC_MIME_TYPES, s3, sha256sum, get_ckan_config_option, get_resource_path,
    wait_for_resource)


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
                    # run in subprocess to circumvent memory leak
                    # https://github.com/DC-analysis/dclab/issues/138
                    # condense(path_out=cond, path_in=path, check_suffix=False)
                    p = multiprocessing.Process(target=condense,
                                                args=(cond, path, True, False))
                    p.start()
                    p.join()
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
