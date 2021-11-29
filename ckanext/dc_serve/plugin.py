from ckan.lib.jobs import _connect as ckan_redis_connect
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from flask import Blueprint
from rq.job import Job

from .cli import get_commands
from . import helpers as dcor_helpers
from .jobs import generate_condensed_resource_job
from .route_funcs import dccondense
from .serve import dcserv


from dcor_shared import DC_MIME_TYPES


class DCServePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IBlueprint)
    plugins.implements(plugins.IClick)
    plugins.implements(plugins.IConfigurer, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)
    plugins.implements(plugins.IActions, inherit=True)
    plugins.implements(plugins.ITemplateHelpers)

    # IBlueprint
    def get_blueprint(self):
        """Return a Flask Blueprint object to be registered by the app."""

        # Create Blueprint for plugin
        blueprint = Blueprint(self.name, self.__module__)

        # Add plugin url rules to Blueprint object
        rules = [
            ('/dataset/<uuid:id>/resource/<uuid:resource_id>/condensed.rtdc',
             'dccondense',
             dccondense),
        ]
        for rule in rules:
            blueprint.add_url_rule(*rule)
        return blueprint

    # IClick
    def get_commands(self):
        return get_commands()

    # IConfigurer
    def update_config(self, config):
        # Add this plugin's templates dir to CKAN's extra_template_paths, so
        # that CKAN will use this plugin's custom templates.
        toolkit.add_template_directory(config, 'templates')

    # IResourceController
    def after_create(self, context, resource):
        """Generate condensed dataset"""
        if resource.get('mimetype') in DC_MIME_TYPES:
            pkg_job_id = f"{resource['package_id']}_{resource['position']}_"
            jid_condense = pkg_job_id + "condense"
            if not Job.exists(jid_condense, connection=ckan_redis_connect()):
                toolkit.enqueue_job(generate_condensed_resource_job,
                                    [resource],
                                    title="Create condensed dataset",
                                    queue="dcor-long",
                                    rq_kwargs={"timeout": 3600,
                                               "job_id": jid_condense})

    # IActions
    def get_actions(self):
        # Registers the custom API method
        return {'dcserv': dcserv}

    # ITemplateHelpers
    def get_helpers(self):
        # Template helper function names should begin with the name of the
        # extension they belong to, to avoid clashing with functions from
        # other extensions.
        hlps = {
            'dc_serve_resource_has_condensed':
                dcor_helpers.resource_has_condensed,
            }
        return hlps
