import multiprocessing

from dclab.cli import condense
from dcor_shared import DC_MIME_TYPES, wait_for_resource, get_resource_path


from .res_file_lock import CKANResourceFileLock


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
                # implemented this is because I wanted to add an automated
                # background job for generating missing condensed files, but
                # then several processes would end up condensing the same
                # resource.
                if fl.is_locked:
                    # run in subprocess to circumvent memory leak
                    # https://github.com/ZELLMECHANIK-DRESDEN/dclab/issues/138
                    # condense(path_out=cond, path_in=path, check_suffix=False)
                    p = multiprocessing.Process(target=condense,
                                                args=(cond, path, False))
                    p.start()
                    p.join()
                    return True
    return False
