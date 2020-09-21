from ckan import logic
import ckan.plugins.toolkit as toolkit

import dclab
from dcor_shared import DC_MIME_TYPES, get_resource_path


# Required so that GET requests work
@toolkit.side_effect_free
def dcserv(context, data_dict=None):
    """Serve DC data as json via the CKAN API

    Required parameters are 'id' (resource id) and
    'query' ('metadata', 'feature_list', 'size', 'trace_list',
    'feature', 'trace', 'valid').
    In case 'query=feature', the parameter 'feature' must
    be set to a valid feature name (e.g. 'feature=deform') and,
    for non-scalar features only, 'event' (event index within
    the dataset) must be set (e.g. 'event=47').
    In case 'query=trace', the 'trace' and 'event' must be set.
    In case 'query=valid', returns True if the resource exists
    and is a valid RT-DC dataset.

    The "result" value will either be a dictionary
    resembling RTDCBase.config (query=metadata),
    a list of available features (query=feature_list),
    or the requested data converted to a list (use
    numpy.asarray to convert back to a numpy array).
    """
    # Perform all authorization checks for the resource
    resource_show = logic.get_action("resource_show")
    resource_show(context, data_dict)
    # Make sure that we are looking at RT-DC data
    model = context['model']
    resource = model.Resource.get(data_dict["id"]).as_dict()
    # Check possible entries in data_dict
    if "query" not in data_dict:
        raise logic.ValidationError("Please specify 'query' parameter")
    query = data_dict["query"]
    if query in ["metadata", "feature_list", "size", "trace_list", "valid"]:
        pass
    elif query == "feature" and "feature" not in data_dict:
        raise logic.ValidationError("Please specify 'feature' parameter")
    elif query == "trace":
        if "trace" not in data_dict:
            raise logic.ValidationError("Please specify 'trace' parameter")
        if "event" not in data_dict:
            raise logic.ValidationError("Please specify 'event' for trace")
        trace = data_dict["trace"]
    elif query == "feature":
        feat = data_dict["feature"]
        if feat not in dclab.dfn.feature_names:
            raise logic.ValidationError("Unknown feature name")
        elif feat not in dclab.dfn.scalar_feature_names:
            if "event" not in data_dict:
                raise logic.ValidationError(
                    "Please specify 'event' for non-scalar features")
    else:
        raise logic.ValidationError("Invalid 'query' parameter")

    # Get the HDF5 file
    path = get_resource_path(resource["id"])
    if query == "valid":
        if path.exists() and resource["mimetype"] in DC_MIME_TYPES:
            data = True
        else:
            data = False
    else:
        if resource["mimetype"] not in DC_MIME_TYPES:
            raise logic.ValidationError("Resource data type not supported")
        path_condensed = path.with_name(path.name + "_condensed.rtdc")
        if path_condensed.exists():
            if (query == "feature" and feat in dclab.dfn.scalar_feature_names):
                # use the condensed dataset for scalar features
                path = path_condensed
            # we need to know the condensed features
            with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path_condensed) as dsc:
                features_condensed = dsc.features_loaded
        else:
            features_condensed = []
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
            if query == "metadata":
                data = dict(ds.config)
            elif query == "feature_list":
                data = sorted(set(ds.features_loaded + features_condensed))
            elif query == "size":
                return len(ds)
            elif query == "trace_list":
                if "trace" in ds:
                    return sorted(ds["trace"].keys())
                else:
                    return []
            elif query == "trace":
                event = int(data_dict["event"])
                data = ds["trace"][trace][event].tolist()
            else:
                if feat in ds.features_loaded:
                    if feat in dclab.dfn.scalar_feature_names:
                        data = ds[feat].tolist()
                    else:
                        event = int(data_dict["event"])
                        data = ds[feat][event].tolist()
                else:
                    raise logic.ValidationError("Feature not available")
    return data
