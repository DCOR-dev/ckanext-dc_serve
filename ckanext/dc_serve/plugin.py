import ckan.plugins as p
import ckan.plugins.toolkit as toolkit

from flask import Blueprint

from .jobs import generate_condensed_dataset_job
from .route_funcs import dccondense
from .serve import dcserv


class DCServePlugin(p.SingletonPlugin):
    p.implements(p.IBlueprint)
    p.implements(p.IResourceController, inherit=True)
    p.implements(p.IActions, inherit=True)

    # IBlueprint
    def get_blueprint(self):
        u'''Return a Flask Blueprint object to be registered by the app.'''

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

    # IResourceController
    def after_create(self, context, resource):
        """Generate preview image and html file"""
        toolkit.enqueue_job(generate_condensed_dataset_job,
                            [resource],
                            title="Create condensed dataset",
                            rq_kwargs={"timeout": 3600})

    # IActions
    def get_actions(self):
        # Registers the custom API method defined above
        return {'dcserv': dcserv}
