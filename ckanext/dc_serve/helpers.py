from dcor_shared import s3cc


def resource_has_condensed(resource_id):
    """Return True if a condensed resource exists"""
    return s3cc.artifact_exists(resource_id, artifact="condensed")
