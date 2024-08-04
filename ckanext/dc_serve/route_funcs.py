import pathlib

import flask
from ckan.common import config, c
import ckan.lib.uploader as uploader
from ckan import logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

import botocore.exceptions
from dcor_shared import s3


def dccondense(ds_id, res_id):
    """Access to the condensed resource

    `ds_id` and `res_id` are strings or uuids.

    If S3 object storage is set up, then the corresponding (presigned)
    URL is returned.
    """
    # Code borrowed from ckan/controllers/package.py:resource_download
    context = {'model': model, 'session': model.Session,
               'user': c.user, 'auth_user_obj': c.userobj}
    did = str(ds_id)
    rid = str(res_id)
    try:
        res_dict = toolkit.get_action('resource_show')(context, {'id': rid})
        ds_dict = toolkit.get_action('package_show')(context, {'id': did})
    except (logic.NotFound, logic.NotAuthorized):
        # Treat not found and not authorized equally, to not leak information
        # to unprivileged users.
        return toolkit.abort(404, toolkit._('Resource not found'))

    res_stem, suffix = res_dict["name"].rsplit(".", 1)
    cond_name = f"{res_stem}_condensed.{suffix}"

    if s3 is not None and res_dict.get('s3_available'):
        # check if the corresponding S3 object exists
        bucket_name = config[
            "dcor_object_store.bucket_name"].format(
            organization_id=ds_dict["organization"]["id"])
        object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
        s3_client, _, _ = s3.get_s3()
        try:
            s3_client.head_object(Bucket=bucket_name,
                                  Key=object_name)
        except botocore.exceptions.ClientError:
            pass
        else:
            # We have an S3 object that we can redirect to. We are making use
            # of presigned URLs to be able to specify a filename for download
            # (otherwise, users that download via the web interface will
            # just get a hash as a file name without any suffix or human-
            # readable identifier).
            if ds_dict["private"]:
                expiration = 3600
            else:
                expiration = 86400
            ps_url = s3.create_presigned_url(
                bucket_name=bucket_name,
                object_name=object_name,
                filename=cond_name,
                expiration=expiration)
            return toolkit.redirect_to(ps_url)

    # We don't have an S3 object, so we have to deliver the internal
    # compressed resource.
    if res_dict.get('url_type') == 'upload':
        upload = uploader.get_resource_uploader(res_dict)
        filepath = pathlib.Path(upload.get_path(res_dict['id']))
        con_file = filepath.with_name(filepath.name + "_condensed.rtdc")
        if not con_file.exists():
            return toolkit.abort(404,
                                 toolkit._('Condensed resource not found'))
        return flask.send_from_directory(con_file.parent, con_file.name,
                                         attachment_filename=cond_name)

    return toolkit.abort(404, toolkit._('No condensed download available'))


def dcresource(ds_id, res_id, name):
    """Access to the resource data

    `ds_id` and `res_id` are strings or uuids.

    If S3 object storage is set up, then the corresponding (presigned)
    URL is returned.

    The `name` parameter is ignored (the `res_id` implies the name, but
    CKAN always has the name here, so we keep it for compatibility)

    This route overrides the default route for downloading a resource from
    CKAN and redirects to S3 if possible.
    """
    # Code borrowed from ckan/controllers/package.py:resource_download
    context = {'model': model, 'session': model.Session,
               'user': c.user, 'auth_user_obj': c.userobj}
    did = str(ds_id)
    rid = str(res_id)
    try:
        res_dict = toolkit.get_action('resource_show')(context, {'id': rid})
        ds_dict = toolkit.get_action('package_show')(context, {'id': did})
    except (logic.NotFound, logic.NotAuthorized):
        # Treat not found and not authorized equally, to not leak information
        # to unprivileged users.
        return toolkit.abort(404, toolkit._('Resource not found'))

    if s3 is not None and res_dict.get('s3_available'):
        # check if the corresponding S3 object exists
        bucket_name = config[
            "dcor_object_store.bucket_name"].format(
            organization_id=ds_dict["organization"]["id"])
        object_name = f"resource/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
        s3_client, _, _ = s3.get_s3()
        try:
            s3_client.head_object(Bucket=bucket_name,
                                  Key=object_name)
        except botocore.exceptions.ClientError:
            pass
        else:
            # We have an S3 object that we can redirect to. We are making use
            # of presigned URLs to be able to specify a filename for download
            # (otherwise, users that download via the web interface will
            # just get a hash as a file name without any suffix or human-
            # readable identifier).
            if ds_dict["private"]:
                expiration = 3600
            else:
                expiration = 86400
            ps_url = s3.create_presigned_url(
                bucket_name=bucket_name,
                object_name=object_name,
                filename=res_dict["name"],
                expiration=expiration)
            return toolkit.redirect_to(ps_url)

    # We don't have an S3 object, so we have to deliver the local
    # resource from block storage.
    if res_dict.get('url_type') == 'upload':
        upload = uploader.get_resource_uploader(res_dict)
        filepath = pathlib.Path(upload.get_path(res_dict['id']))
        if not filepath.exists():
            return toolkit.abort(404, toolkit._('Resource not found'))
        return flask.send_from_directory(filepath.parent, filepath.name,
                                         attachment_filename=res_dict["name"])

    return toolkit.redirect_to(res_dict["url"])
