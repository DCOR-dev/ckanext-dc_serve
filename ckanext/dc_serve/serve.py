import atexit
import functools
import io
import warnings

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

import dclab
from dclab.rtdc_dataset import linker as dclab_linker
from dcor_shared import (
    DC_MIME_TYPES, get_resource_path, get_ckan_config_option, s3)
import h5py
import numpy as np


def admin_context():
    return {'ignore_auth': True, 'user': 'default'}


def get_rtdc_instance(res_id, force_s3=False):
    """Return instance of RTDCBase

    See Also
    --------
    get_rtdc_instance_local: get file linked to data on block storage
    get_rtdc_instance_local: get file with basins from S3
    """
    # First check whether we have a local file. Local files should be
    # faster to access, so we favor this scenario.
    path = get_resource_path(res_id)
    if path.exists() and not force_s3:
        return get_rtdc_instance_local(res_id)
    else:
        return get_rtdc_instance_s3(res_id)


@functools.lru_cache(maxsize=100)
def get_rtdc_instance_local(res_id):
    """Return an instance of RTDCBase for the given resource identifier

    The `rid` identifier is used to resolve the uploaded .rtdc file.
    Using :func:`combined_h5`, the condensed .rtdc file is merged with
    this .rtdc file into a new in-memory file which is opened with dclab.

    This method is cached using an `lru_cache`, so consecutive calls
    with the same identifier should be fast.

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


@functools.lru_cache(maxsize=100)
def get_rtdc_instance_s3(res_id):
    """Same as `get_rtdc_instance_local`, except that data are taken from S3

    The `rid` identifier is used to identify the S3 object store key.

    This method does not create an HDF5 file that contains links to
    datasets on S3, but instead uses basins that were introduced in
    dclab 0.53.0.

    This method is cached using an `lru_cache`, so consecutive calls
    with the same identifier should be fast.
    """
    rid = res_id
    res_dict = toolkit.get_action("resource_show")(context=admin_context(),
                                                   data_dict={"id": rid})
    ds_dict = toolkit.get_action("package_show")(
        context=admin_context(), data_dict={"id": res_dict["package_id"]})
    endpoint = get_ckan_config_option("dcor_object_store.endpoint_url")
    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    object_names = [f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}",
                    f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"]

    # build metadata dictionary from resource metadata
    meta = {}
    for item in res_dict:
        if item.startswith("dc:"):
            _, sec, key = item.split(":", 2)
            meta.setdefault(sec, {})
            meta[sec][key] = res_dict[item]

    basin_paths = []
    for on in object_names:
        if ds_dict["private"]:
            bp = s3.create_presigned_url(bucket_name=bucket_name,
                                         object_name=on)
        else:
            bp = f"{endpoint}/{bucket_name}/{on}"
        basin_paths.append(bp)

    fd = io.BytesIO()
    with h5py.File(fd, "w", libver="latest") as hv:
        # We don't use RTDCWriter as a context manager to avoid overhead
        # during __exit__, but then we have to make sure "events" is there.
        hv.require_group("events")
        hw = dclab.RTDCWriter(hv)
        hw.store_metadata(meta)
        for on, bp in zip(object_names, basin_paths):
            hw.store_basin(basin_name=on.split("/")[0],
                           basin_format="http",
                           basin_type="remote",
                           basin_locs=[bp],
                           # Don't verify anything. This would only cost time,
                           # and we know these objects exist.
                           verify=False,
                           )
    return dclab.rtdc_dataset.fmt_hdf5.RTDC_HDF5(fd)


def get_rtdc_logs(ds, from_basins=False):
    """Return logs of a dataset, optionally looking only in its basins"""
    logs = {}
    if from_basins:
        for bn in ds.basins:
            if bn.is_available():
                logs.update(get_rtdc_logs(bn.ds))
    else:
        # all the features are
        logs.update(dict(ds.logs))
    return logs


def get_rtdc_tables(ds, from_basins=False):
    """Return tables of a dataset, optionally looking only in its basins"""
    tables = {}
    if from_basins:
        for bn in ds.basins:
            if bn.is_available():
                tables.update(get_rtdc_tables(bn.ds))
    else:
        for tab in ds.tables:
            tables[tab] = (ds.tables[tab].dtype.names,
                           ds.tables[tab][:].tolist())
    return tables


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
     - 'basins': list of basin dictionaries (upstream and http data)
     - 'trace_list': list of available traces
     - 'valid': whether the corresponding .rtdc file is accessible.
     - 'version': which version of the API to use (defaults to 1);
        If you specify '2' and the resource and condensed resources are
        on S3, then no feature data is served via the API, only basins
        (on S3) are specified via the "http" remote.

    The "result" value will either be a dictionary
    resembling RTDCBase.config (e.g. query=metadata),
    a list of available features (query=feature_list),
    or the requested data converted to a list (use
    numpy.asarray to convert back to a numpy array).
    """
    if data_dict is None:
        data_dict = {}
    data_dict.setdefault("version", "1")

    # Check required parameters
    if "query" not in data_dict:
        raise logic.ValidationError("Please specify 'query' parameter!")
    if "id" not in data_dict:
        raise logic.ValidationError("Please specify 'id' parameter!")
    if data_dict["version"] not in ["1", "2"]:
        raise logic.ValidationError("Please specify version '1' or '2'!")

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

    version_is_2 = data_dict["version"] == "2"

    if query == "valid":
        path = get_resource_path(res_id)
        data = path.exists()
    else:
        ds = get_rtdc_instance(res_id, force_s3=version_is_2)
        if query == "feature":
            if version_is_2:
                # We are forcing the usage of basins in the client.
                raise logic.ValidationError(
                    "Features unavailable, use basins!")
            else:
                data = get_feature_data(data_dict, ds)
        elif query == "feature_list":
            if version_is_2:
                data = []
            else:
                data = ds.features_loaded
        elif query == "logs":
            data = get_rtdc_logs(ds, from_basins=version_is_2)
        elif query == "metadata":
            data = ds.config.as_dict(pop_filtering=True)
        elif query == "size":
            data = len(ds)
        elif query == "basins":
            # Return all basins from the condensed file
            # (the S3 basins are already in there).
            data = ds.basins_get_dicts()
        elif query == "tables":
            data = get_rtdc_tables(ds, from_basins=version_is_2)
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


atexit.register(get_rtdc_instance_local.cache_clear)
atexit.register(get_rtdc_instance_s3.cache_clear)
atexit.register(is_rtdc_resource.cache_clear)
