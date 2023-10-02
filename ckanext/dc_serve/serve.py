import functools
import json
import warnings

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

import dclab
from dclab.rtdc_dataset import linker as dclab_linker
from dcor_shared import DC_MIME_TYPES, get_resource_path
import numpy as np


def get_rtdc_instance(res_id):
    """Return an instance of RTDCBase for the given resource identifier

    The `rid` identifier is used to resolve the uploaded .rtdc file.
    Using :func:`combined_h5`, the condensed .rtdc file is merged with
    this .rtdc file into a new in-memory file which is opened with dclab.

    This method is cached using an `lru_cache`, so consecutive calls
    with the same identifier should be fast.

    `user_id` is only used for caching.

    This whole process takes approximately 20ms:

    Per Hit  % Time  Line Contents
    1.8      0.0   path_list = ["calibration_beads_condensed.rtdc", path_name]
    11915.4  57.4  h5io = combined_h5(path_list)
    8851.6   42.6  return dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(h5io)
    """
    path = get_resource_path(res_id)
    paths = [path]

    path_condensed = path.with_name(path.name + "_condensed.rtdc")
    if path_condensed.exists():
        paths.append(path_condensed)

    h5io = dclab_linker.combine_h5files(paths, external="raise")
    return dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(h5io)


# Required so that GET requests work
@toolkit.side_effect_free
def dcserv(context, data_dict=None):
    """Serve DC data as json via the CKAN API

    Required key in `data_doct` are 'id' (resource id) and
    'query'. Query may be one of the following:
     - 'feature', in which case the 'feature' parameter must be set
       to a valid feature name (e.g. `query=feature&feature=deform`).
       Returns feature data. If the feature is not a scalar feature,
       then 'event' (index) must also be given
       (e.g. `query=feature&feature=image&event=42`). In case of
       'feature=trace', then in addition to the 'event' key, the
       'trace' key (e.g. 'trace=fl1_raw') must also be set.
     - 'feature_list': a list of available features
     - 'logs': dictionary of logs
     - 'metadata': the metadata configuration dictionary
     - 'size': the number of events in the dataset
     - 'tables': dictionary of tables (each entry consists of a tuple
        with the column names and the array data)
     - 'trace_list': list of available traces
     - 'valid': whether the corresponding .rtdc file is accessible.

    The "result" value will either be a dictionary
    resembling RTDCBase.config (e.g. query=metadata),
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

    # Check whether we actually have an .rtdc dataset
    if not is_rtdc_resource(res_id):
        raise logic.ValidationError(
            f"Resource ID {res_id} must be an .rtdc dataset!")

    if query == "valid":
        path = get_resource_path(res_id)
        data = path.exists()
    else:
        with get_rtdc_instance(res_id) as ds:
            if query == "feature":
                data = get_feature_data(data_dict, ds)
            elif query == "feature_list":
                data = ds.features_loaded
            elif query == "logs":
                data = dict(ds.logs)
            elif query == "metadata":
                data = json.loads(ds.config.tojson())
            elif query == "size":
                data = len(ds)
            elif query == "tables":
                data = {}
                for tab in ds.tables:
                    data[tab] = (ds.tables[tab].dtype.names,
                                 ds.tables[tab][:].tolist())
            elif query == "trace":
                warnings.warn("A dc_serve client is using the 'trace' query!",
                              DeprecationWarning)
                # backwards-compatibility
                data_dict["query"] = "feature"
                data_dict["feature"] = "trace"
                data = get_feature_data(data_dict, ds)
            elif query == "trace_list":
                if "trace" in ds:
                    data = sorted(ds["trace"].keys())
                else:
                    data = []
            else:
                raise logic.ValidationError(
                    f"Invalid query parameter '{query}'!")
    return data


@functools.lru_cache(maxsize=1024)
def is_rtdc_resource(res_id):
    resource = model.Resource.get(res_id)
    return resource.mimetype in DC_MIME_TYPES


def get_feature_data(data_dict, ds):
    query = data_dict["query"]
    # sanity checks
    if query == "feature" and "feature" not in data_dict:
        raise logic.ValidationError("Please specify 'feature' parameter!")

    feat = data_dict["feature"]
    is_scalar = dclab.dfn.scalar_feature_exists(feat)

    if feat in ds.features_loaded:
        if is_scalar:
            data = np.array(ds[feat]).tolist()
        else:
            if "event" not in data_dict:
                raise logic.ValidationError("Please specify 'event' for "
                                            + f"non-scalar feature {feat}!"
                                            )
            if feat == "trace":
                data = get_trace_data(data_dict, ds)
            else:
                event = int(data_dict["event"])
                data = ds[feat][event].tolist()
    elif not dclab.dfn.feature_exists(feat):
        raise logic.ValidationError(f"Unknown feature name '{feat}'!")
    else:
        raise logic.ValidationError(f"Feature '{feat}' unavailable!")
    return data


def get_trace_data(data_dict, ds):
    if "trace" not in data_dict:
        raise logic.ValidationError("Please specify 'trace' parameter!")
    event = int(data_dict["event"])
    trace = data_dict["trace"]

    data = ds["trace"][trace][event].tolist()
    return data
