from ckan.lib.jobs import _connect as ckan_redis_connect
import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit

from flask import Blueprint
from rq.job import Job

from .cli import get_commands
from . import helpers as dcor_helpers
from .jobs import generate_condensed_resource_job, migrate_condensed_to_s3_job
from .route_funcs import dccondense, dcresource
from .serve import dcserv


from dcor_shared import DC_MIME_TYPES, s3


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
            ('/dataset/<uuid:ds_id>/resource/<uuid:res_id>/condensed.rtdc',
             'dccondense',
             dccondense),
            ('/dataset/<uuid:ds_id>/resource/<uuid:res_id>/download/<name>',
             'dcresource',
             dcresource),
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
    def after_resource_create(self, context, resource):
        """Generate condensed dataset"""
        if resource.get('mimetype') in DC_MIME_TYPES:
            # Generate the condensed dataset
            pkg_job_id = f"{resource['package_id']}_{resource['position']}_"
            jid_condense = pkg_job_id + "condense"
            jid_symlink = pkg_job_id + "symlink"
            if not Job.exists(jid_condense, connection=ckan_redis_connect()):
                toolkit.enqueue_job(generate_condensed_resource_job,
                                    [resource],
                                    title="Create condensed dataset",
                                    queue="dcor-long",
                                    rq_kwargs={"timeout": 3600,
                                               "job_id": jid_condense,
                                               "depends_on": [jid_symlink]})

            # Upload the condensed dataset to S3
            if s3.is_available():
                jid_condensed_s3 = pkg_job_id + "condenseds3"
                toolkit.enqueue_job(
                    migrate_condensed_to_s3_job,
                    [resource],
                    title="Migrate condensed resource to S3 object store",
                    queue="dcor-normal",
                    rq_kwargs={"timeout": 1000,
                               "job_id": jid_condensed_s3,
                               "depends_on": [
                                   # symlink is general requirement
                                   jid_symlink,
                                   jid_condense,
                               ]}
                    )

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
