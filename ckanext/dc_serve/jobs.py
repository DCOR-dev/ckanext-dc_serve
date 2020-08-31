import pathlib

from dclab.cli import condense
from dcor_shared import DC_MIME_TYPES, wait_for_resource


def generate_condensed_dataset_job(path, resource, override=False):
    """Generates a condensed version of the dataset"""
    path = pathlib.Path(path)
    if resource["mimetype"] in DC_MIME_TYPES:
        wait_for_resource(path)
        cond = path.with_name(path.name + "_condensed.rtdc")
        if not cond.exists() or override:
            condense(path_in=path, path_out=cond)
