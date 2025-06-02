import atexit
import copy
import functools
import logging
import time

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

from dcor_shared import (
    DC_MIME_TYPES, s3cc, is_resource_private,
)


logger = logging.getLogger(__name__)


def admin_context():
    return {'ignore_auth': True, 'user': 'default'}


def get_dc_logs(ds, from_basins: bool = False) -> dict:
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


def get_dc_tables(ds, from_basins: bool = False) -> dict:
    """Return tables of a dataset, optionally looking only in its basins"""
    tables = {}
    if from_basins:
        for bn in ds.basins:
            if bn.is_available():
                tables.update(get_dc_tables(bn.ds))
    else:
        for tab in ds.tables:
            tables[tab] = (ds.tables[tab].keys(),
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
        return get_resource_kernel(rid)["config"]
    else:
        if query == "feature_list":
            # Don't return any features. Basins are responsible.
            data = []
        elif query == "logs":
            data = get_resource_kernel(rid)["logs"]
        elif query == "size":
            data = get_resource_kernel(
                rid)["config"]["experiment"]["event count"]
        elif query == "basins":
            r_data = get_resource_kernel(rid)
            # Return all basins from the condensed file
            # (the S3 basins are already in there).
            if r_data["public"] and "basin_dicts" in r_data:
                # We have a public resource and a complete set of basins.
                data = copy.deepcopy(r_data["basin_dicts"])
            else:
                # We have a private resource and must work with presigned URLs.
                # The basins just links to the original resource and
                # condensed file.
                data = get_resource_basins_dicts_private(rid)
            # populate the basin features in-place
            basin_features = r_data["basin_features"]
            for bn_dict in data:
                name = bn_dict["name"]
                if name in basin_features:
                    bn_dict["features"] = basin_features[name]
        elif query == "tables":
            data = get_resource_kernel(rid)["tables"]
        elif query == "trace_list":
            data = get_resource_kernel(rid)["trace_list"]
        else:
            raise logic.ValidationError(
                f"Invalid query parameter '{query}'!")
    return data


@functools.lru_cache(maxsize=1024)
def is_dc_resource(res_id) -> bool:
    resource = model.Resource.get(res_id)
    return resource.mimetype in DC_MIME_TYPES


def get_resource_basins_dicts_private(resource_id):
    """Return list of private resource basin dicts

    Note that the condensed resource comes first in the list.
    """
    basin_dicts = []
    for artifact in ["condensed", "resource"]:
        time_request = time.time()
        signed_url, expires_at = s3cc.create_presigned_url(
            resource_id,
            artifact=artifact,
            expiration=3600,
            ret_expiration=True
            )
        basin_dicts.append({
            "name": f"{artifact}-{resource_id[:5]}",
            "format": "http",
            "type": "remote",
            "mapping": "same",
            "perishable": True,
            "time_request": time_request,
            "time_expiration": expires_at,
            "key": f"dcor-presigned-{artifact}-{resource_id}",
            "urls": [signed_url],
        })
    return basin_dicts


def get_resource_kernel(resource_id: str) -> dict:
    """Return dictionary with most important resource information"""
    public = not is_resource_private(resource_id)
    # TODO: Caching `get_resource_kernel_base` is potentially bad for
    #       memory. Consider storing the data in redis or a local disk cache.
    r_data = get_resource_kernel_base(resource_id, public=public)

    # The dictionary `r_data` is cached in `get_resource_kernel_base`.
    # If we complement it, then we modify this dictionary in the cache.
    # This is fine. It also means we do not have to cache the result
    # of `get_resource_kernel_complement_condensed`.
    if not r_data.get("complemented-condensed"):
        try:
            get_resource_kernel_complement_condensed(r_data)
        except BaseException:
            logger.warning(
                f"Failed to fetch condensed resource info for {resource_id}")

    return r_data


@functools.lru_cache(maxsize=512)
def get_resource_kernel_base(resource_id, public: bool = False):
    """Return dictionary with most important resource information

    This method is cached. Complementary information can be added
    via :func:`get_resource_kernel_complement_condensed`.
    """
    r_data = {"id": resource_id,
              "public": public}

    ds_res = s3cc.get_s3_dc_handle(resource_id, artifact="resource")

    # configuration
    r_data["config"] = ds_res.config.as_dict(pop_filtering=True)
    r_data["config"].setdefault("experiment", {})
    if not r_data["config"]["experiment"]["event count"]:
        r_data["config"]["experiment"]["event count"] = len(ds_res)
    # trace list
    if "trace" in ds_res:
        r_data["trace_list"] = sorted(ds_res["trace"].keys())
    # tables
    r_data["tables"] = get_dc_tables(ds_res, from_basins=False)
    # logs
    r_data["logs"] = get_dc_logs(ds_res, from_basins=False)
    # basin features
    basin_features = {
        f"resource-{resource_id[:5]}": ds_res.features_innate,
    }
    r_data["basin_features"] = basin_features
    # basins (for public resources only, since we don't need presigned URLs)
    if public:
        # The condensed resource should come first, because it
        # probably has better chunking / data access via HTTP.
        # Note that we can add the condensed resource here, even
        # if it is not yet available.
        basin_urls = {
            "condensed": ds_res.path.replace("/resource/", "/condensed/"),
            "resource": ds_res.path,
        }
        basins_dicts = []
        for artifact in basin_urls:
            basins_dicts.append({
                "name": f"{artifact}-{resource_id[:5]}",
                "format": "http",
                "type": "remote",
                "mapping": "same",
                "perishable": False,
                "key": f"dcor-{artifact}-{resource_id}",
                "urls": [basin_urls[artifact]],
            })
        r_data["basin_dicts"] = basins_dicts

    return r_data


def get_resource_kernel_complement_condensed(r_data):
    """Complement dictionary with condensed resource information

    The input dictionary is expected to be created via
    :func:`get_resource_kernel_base`.
    """
    resource_id = r_data["id"]
    ds_con = s3cc.get_s3_dc_handle(resource_id, artifact="condensed")
    # condense logs
    new_logs = get_dc_logs(ds_con, from_basins=False)
    for ln in new_logs:
        if ln not in r_data["logs"]:
            r_data["logs"][ln] = new_logs[ln]
    # basin features
    r_data["basin_features"][f"condensed-{resource_id[:5]}"] = \
        ds_con.features_innate
    r_data["complemented-condensed"] = True


atexit.register(is_dc_resource.cache_clear)
atexit.register(get_resource_kernel_base.cache_clear)
