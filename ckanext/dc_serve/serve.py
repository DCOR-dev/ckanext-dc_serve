import atexit
import functools

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

from dcor_shared import DC_MIME_TYPES, get_resource_dc_config, s3cc


def admin_context():
    return {'ignore_auth': True, 'user': 'default'}


def get_dc_logs(ds, from_basins=False):
    """Return logs of a dataset, optionally looking only in its basins"""
    logs = {}
    if from_basins:
        for bn in ds.basins:
            if bn.is_available():
                logs.update(get_dc_logs(bn.ds))
    else:
        # all the features are
        logs.update(dict(ds.logs))
    return logs


def get_dc_tables(ds, from_basins=False):
    """Return tables of a dataset, optionally looking only in its basins"""
    tables = {}
    if from_basins:
        for bn in ds.basins:
            if bn.is_available():
                tables.update(get_dc_tables(bn.ds))
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

     - 'logs': dictionary of logs
     - 'metadata': the metadata configuration dictionary
     - 'size': the number of events in the dataset
     - 'tables': dictionary of tables (each entry consists of a tuple
        with the column names and the array data)
     - 'basins': list of basin dictionaries (upstream and http data)
     - 'trace_list': list of available traces
     - 'valid': whether the corresponding .rtdc file is accessible.
     - 'version': which version of the API to use (defaults to 2);

    .. versionchanged: 0.15.0

        Drop support for DCOR API version 1

    The "result" value will either be a dictionary
    resembling RTDCBase.config (e.g. query=metadata),
    a list of available traces (query=trace_list),
    or the requested data converted to a list (use
    numpy.asarray to convert back to a numpy array).
    """
    if data_dict is None:
        data_dict = {}
    data_dict.setdefault("version", "2")

    # Check required parameters
    if "query" not in data_dict:
        raise logic.ValidationError("Please specify 'query' parameter!")
    if "id" not in data_dict:
        raise logic.ValidationError("Please specify 'id' parameter!")
    if data_dict["version"] == "1":
        raise logic.ValidationError("Version '1' of the DCOR API is not "
                                    "supported anymore. Please use version "
                                    "'2' instead!")
    if data_dict["version"] not in ["2"]:
        raise logic.ValidationError("Please specify version '1' or '2'!")

    # Perform all authorization checks for the resource
    logic.check_access("resource_show",
                       context=context,
                       data_dict={"id": data_dict["id"]})

    query = data_dict["query"]
    rid = data_dict["id"]

    # Check whether we actually have an .rtdc dataset
    if not is_dc_resource(rid):
        raise logic.ValidationError(
            f"Resource ID {rid} must be an .rtdc dataset!")

    if query == "valid":
        data = s3cc.artifact_exists(rid, artifact="resource")
    elif query == "metadata":
        return get_resource_dc_config(rid)
    else:
        if query == "feature_list":
            data = []
        elif query == "logs":
            with s3cc.get_s3_dc_handle_basin_based(rid) as ds:
                data = get_dc_logs(ds, from_basins=True)
        elif query == "size":
            with s3cc.get_s3_dc_handle(rid) as ds:
                data = len(ds)
        elif query == "basins":
            # Return all basins from the condensed file
            # (the S3 basins are already in there).
            with s3cc.get_s3_dc_handle_basin_based(rid) as ds:
                # The basins just links to the original resource and
                # condensed file.
                data = ds.basins_get_dicts()
        elif query == "tables":
            with s3cc.get_s3_dc_handle_basin_based(rid) as ds:
                data = get_dc_tables(ds, from_basins=True)
        elif query == "trace_list":
            with s3cc.get_s3_dc_handle(rid) as ds:
                if "trace" in ds:
                    data = sorted(ds["trace"].keys())
                else:
                    data = []
        else:
            raise logic.ValidationError(
                f"Invalid query parameter '{query}'!")
    return data


@functools.lru_cache(maxsize=1024)
def is_dc_resource(res_id):
    resource = model.Resource.get(res_id)
    return resource.mimetype in DC_MIME_TYPES


atexit.register(is_dc_resource.cache_clear)
