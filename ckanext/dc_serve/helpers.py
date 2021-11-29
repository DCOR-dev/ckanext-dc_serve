import dcor_shared


def resource_has_condensed(resource_id):
    rpath = dcor_shared.get_resource_path(resource_id)
    return rpath.with_name(rpath.stem + "_condensed.rtdc").exists()
