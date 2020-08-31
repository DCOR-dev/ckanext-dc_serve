import pathlib

import flask
from ckan.common import c
import ckan.lib.uploader as uploader
from ckan import logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit


def dccondense(id, resource_id):
    """Access to the condensed dataset

    `id` and `resource_id` are strings or uuids.
    """
    # Code borrowed from ckan/controllers/package.py:resource_download
    context = {'model': model, 'session': model.Session,
               'user': c.user, 'auth_user_obj': c.userobj}
    id = str(id)
    resource_id = str(resource_id)
    try:
        rsc = toolkit.get_action('resource_show')(context, {'id': resource_id})
        toolkit.get_action('package_show')(context, {'id': id})
    except (logic.NotFound, logic.NotAuthorized):
        toolkit.abort(404, toolkit._('Resource not found'))

    if rsc.get('url_type') == 'upload':
        upload = uploader.get_resource_uploader(rsc)
        filepath = pathlib.Path(upload.get_path(rsc['id']))
        con_file = filepath.with_name(filepath.name + "_condensed.rtdc")
        if not con_file.exists():
            toolkit.abort(404, toolkit._('Preview not found'))
        return flask.send_from_directory(con_file.parent, con_file.name)
    elif 'url' not in rsc:
        toolkit.abort(404, toolkit._('No download is available'))
    toolkit.redirect_to(rsc['url'])
