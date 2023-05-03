import functools
import io
import json
import pathlib
import warnings

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

import dclab
from dcor_shared import DC_MIME_TYPES, get_resource_path
import h5py
import numpy as np


class ExternalLinksForbiddenError(BaseException):
    """Raised when a dataset contains external links

    External links pose a security thread, because they could be
    used to access data that is not supposed to be accessed. On
    the file system level, we don't have CKAN authentication.
    """
    pass


def check_external_links(h5):
    """Check recursively, whether an h5py object contains external links

    Returns a tuple of either
    - `(True, path_el)` if the object contains an external link
    - `(False, None)` if this is not the case
    """
    for obj in h5:
        if isinstance(obj, h5py.ExternalLink):
            # The group or the dataset is an external link
            return True, obj.path
        elif isinstance(obj, h5py.Group):
            # Check all the objects within this group
            has_el, path_el = check_external_links(obj)
            if has_el:
                return True, path_el
    else:
        return False, None


def combined_h5(paths):
    """Create an in-memory file that combines raw and condensed .rtdc files

    Parameters
    ----------
    paths: list of str or pathlib.Path
        Paths of the input .rtdc files. The first input file is always
        used as a source for the metadata. The other files only complement
        the features.

    Notes
    -----
    This method checks for the existence of HDF5 external links. These
    should not be used here, because they could potentially lead to
    data leakage.
    """
    fd = io.BytesIO()
    with h5py.File(fd, "w", libver="latest") as hv:
        for ii, pp in enumerate(paths):
            pp = pathlib.Path(pp).resolve()
            with h5py.File(pp, libver="latest") as h5:
                # Check for external links
                has_el, path_el = check_external_links(h5)
                if has_el:
                    raise ExternalLinksForbiddenError(
                        f"Dataset {pp} contains external links, but these "
                        f"are not permitted for safety reasons ({path_el})!")
                if ii == 0:
                    # Only write attributes once.
                    # Interestingly, writing the attributes takes
                    # the most time. Maybe there is some shortcut
                    # than can be taken (since e.g. we know we don't have to
                    # check for existing attributes).
                    # https://github.com/h5py/h5py/blob/master/
                    # h5py/_hl/attrs.py
                    hv.attrs.update(h5.attrs)
                    # Also, write logs/tables/... (anything that is
                    # not events) only once.
                    for group in h5:
                        if group != "events":
                            hv[group] = h5py.ExternalLink(str(pp), group)
                # Append features
                hve = hv.require_group("events")
                for feat in h5["events"]:
                    if feat not in hve:
                        hve[feat] = h5py.ExternalLink(str(pp),
                                                      f"/events/{feat}")
    return fd


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

    h5io = combined_h5(paths)
    return dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(h5io)


# Required so that GET requests work
@toolkit.side_effect_free
def dcserv(context, data_dict=None):
    """Serve DC data as json via the CKAN API

    Required key in `data_doct` are 'id' (resource id) and
    'query'. Query may be one of the following:
     - 'feature', in which case the 'feature' parameter must be set
       set to a valid feature name (e.g. `query=feature&feature=deform`).
       Returns feature data. If the feature is not a scalar feature,
       then 'event' (index) must also be given
       (e.g. `query=feature&feature=image&event=42`. In case of
       'feature=trace', then in addition to the 'event' key, the
       'trace' key (e.g. 'trace=fl1_raw') must also be set.
     - 'feature_list': a list of available features
     - 'logs': dictionary of logs
     - 'metadata': the metadata configuration dictionary
     - 'size': the number of events in the dataset
     - 'tables': dictionary of tables
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
