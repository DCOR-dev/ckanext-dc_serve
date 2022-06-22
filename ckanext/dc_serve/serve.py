import functools
import json
import warnings

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

import dclab
from dcor_shared import DC_MIME_TYPES, get_resource_path
import numpy as np


# Required so that GET requests work
@toolkit.side_effect_free
def dcserv(context, data_dict=None):
    """Serve DC data as json via the CKAN API

    Required parameters are 'id' (resource id) and
    'query' ('feature', 'feature_list', 'metadata', 'size',
    'trace', 'trace_list', 'valid').

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
    # Check required parameters
    if "query" not in data_dict:
        raise logic.ValidationError("Please specify 'query' parameter!")
    if "id" not in data_dict:
        raise logic.ValidationError("Please specify 'id' parameter!")

    # Perform all authorization checks for the resource
    logic.check_access("resource_show",
                       context=context,
                       data_dict={"id": data_dict["id"]})

    query = data_dict["query"]
    res_id = data_dict["id"]
    path = get_resource_path(res_id)

    # Check whether we actually have an .rtdc dataset
    if not is_rtdc_resource(res_id):
        raise logic.ValidationError(
            f"Resource ID {res_id} must be an .rtdc dataset!")

    if query == "feature":
        data = get_feature_data(data_dict, path)
    elif query == "feature_list":
        data = get_feature_list(path)
    elif query == "metadata":
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
            data = json.loads(ds.config.tojson())
    elif query == "size":
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
            data = len(ds)
    elif query == "trace":
        warnings.warn("A dc_serve client is using the 'trace' query!",
                      DeprecationWarning)
        # backwards-compatibility
        data_dict["query"] = "feature"
        data_dict["feature"] = "trace"
        data = get_feature_data(data_dict, path)
    elif query == "trace_list":
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
            if "trace" in ds:
                data = sorted(ds["trace"].keys())
            else:
                data = []
    elif query == "valid":
        data = path.exists()
    else:
        raise logic.ValidationError(f"Invalid query parameter '{query}'!")

    return data


@functools.lru_cache(maxsize=1024)
def is_rtdc_resource(res_id):
    resource = model.Resource.get(res_id)
    return resource.mimetype in DC_MIME_TYPES


@functools.lru_cache(maxsize=128)
def get_feature_list(path):
    path_condensed = path.with_name(path.name + "_condensed.rtdc")
    if path_condensed.exists():
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path_condensed) as dsc:
            features_condensed = dsc.features_loaded
    else:
        features_condensed = []
    with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
        features_original = ds.features_loaded
    return sorted(set(features_condensed + features_original))


def get_feature_data(data_dict, path):
    query = data_dict["query"]
    # sanity checks
    if query == "feature" and "feature" not in data_dict:
        raise logic.ValidationError("Please specify 'feature' parameter!")

    feat = data_dict["feature"]
    is_scalar = dclab.dfn.scalar_feature_exists(feat)
    path_condensed = path.with_name(path.name + "_condensed.rtdc")

    if is_scalar and path_condensed.exists():
        path = path_condensed

    feature_list = get_feature_list(path)
    if feat in feature_list:
        with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
            if is_scalar:
                data = np.array(ds[feat]).tolist()
            else:
                if "event" not in data_dict:
                    raise logic.ValidationError("Please specify 'event' for "
                                                + f"non-scalar feature {feat}!"
                                                )
                if feat == "trace":
                    data = get_trace_data(data_dict, path)
                else:
                    event = int(data_dict["event"])
                    data = ds[feat][event].tolist()
    elif not dclab.dfn.feature_exists(feat):
        raise logic.ValidationError(f"Unknown feature name '{feat}'!")
    else:
        raise logic.ValidationError(f"Feature '{feat}' unavailable!")
    return data


def get_trace_data(data_dict, path):
    if "trace" not in data_dict:
        raise logic.ValidationError("Please specify 'trace' parameter!")
    event = int(data_dict["event"])
    trace = data_dict["trace"]

    with dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(path) as ds:
        data = ds["trace"][trace][event].tolist()
    return data
