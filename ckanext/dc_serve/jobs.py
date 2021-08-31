import multiprocessing

from dclab.cli import condense
from dcor_shared import DC_MIME_TYPES, wait_for_resource, get_resource_path


def generate_condensed_resource_job(resource, override=False):
    """Generates a condensed version of the dataset"""
    path = get_resource_path(resource["id"])
    if resource["mimetype"] in DC_MIME_TYPES:
        wait_for_resource(path)
        cond = path.with_name(path.name + "_condensed.rtdc")
        if not cond.exists() or override:
            # run in subprocess to circumvent memory leak
            # (https://github.com/ZELLMECHANIK-DRESDEN/dclab/issues/138)
            # condense(path_out=cond, path_in=path, check_suffix=False)
            p = multiprocessing.Process(target=condense,
                                        args=(cond, path, False))
            p.start()
            p.join()
            return True
    return False
