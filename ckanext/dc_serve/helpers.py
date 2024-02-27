from dcor_shared import get_resource_path, s3cc


def resource_has_condensed(resource_id):
    """Return True if a condensed resource exists"""
    rpath = get_resource_path(resource_id)
    cpath = rpath.with_name(rpath.stem + "_condensed.rtdc")
    return (
        # block storage existence
        cpath.exists()
        # S3 existence
        or s3cc.artifact_exists(resource_id, artifact="condensed")
    )
