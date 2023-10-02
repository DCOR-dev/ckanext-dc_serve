import pathlib

import flask
from ckan.common import c
import ckan.lib.uploader as uploader
from ckan import logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit

from dcor_shared import get_ckan_config_option, s3


def dccondense(id, resource_id):
    """Access to the condensed dataset

    `id` and `resource_id` are strings or uuids.

    If S3 object storage is set up, then the corresponding (presigned)
    URL is returned.
    """
    # Code borrowed from ckan/controllers/package.py:resource_download
    context = {'model': model, 'session': model.Session,
               'user': c.user, 'auth_user_obj': c.userobj}
    id = str(id)
    resource_id = str(resource_id)
    try:
        res_dict = toolkit.get_action('resource_show')(context,
                                                       {'id': resource_id})
        ds_dict = toolkit.get_action('package_show')(context, {'id': id})
    except (logic.NotFound, logic.NotAuthorized):
        # Treat not found and not authorized equally, to not leak information
        # to unprivileged users.
        toolkit.abort(404, toolkit._('Resource not found'))
        return

    if s3 is not None and res_dict.get('s3_available'):
        # check if the corresponding S3 object exists
        bucket_name = get_ckan_config_option(
            "dcor_object_store.bucket_name").format(
            organization_id=ds_dict["organization"]["id"])
        rid = resource_id
        object_name = f"condensed/{rid[:3]}/{rid[3:6]}/{rid[6:]}"
        s3_client, _, _ = s3.get_s3()
        try:
            s3_client.head_object(Bucket=bucket_name,
                                  Key=object_name)
        except s3_client.exceptions.NoSuchKey:
            pass
        else:
            # We have an S3 object that we can redirect to
            if ds_dict["private"]:
                # generate a presigned S3 url
                ps_url = s3.create_presigned_url(
                    bucket_name=bucket_name,
                    object_name=object_name)
                return toolkit.redirect_to(ps_url)
            else:
                # return the public URL of the condensed object
                obj_url = res_dict["s3_url"].replace("/resource/",
                                                     "/condensed/")
                return toolkit.redirect_to(obj_url)

    # We don't have an S3 object, so we have to deliver the internal
    # compressed resource.
    if res_dict.get('url_type') == 'upload':
        upload = uploader.get_resource_uploader(res_dict)
        filepath = pathlib.Path(upload.get_path(res_dict['id']))
        con_file = filepath.with_name(filepath.name + "_condensed.rtdc")
        if not con_file.exists():
            toolkit.abort(404, toolkit._('Preview not found'))
        return flask.send_from_directory(con_file.parent, con_file.name)

    return toolkit.abort(404, toolkit._('No download is available'))
