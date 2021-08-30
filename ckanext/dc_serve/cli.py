import ckan.model as model

import click


from . import jobs


def click_echo(message, am_on_a_new_line):
    if not am_on_a_new_line:
        click.echo("")
    click.echo(message)


@click.command()
def run_jobs_dc_view():
    """Compute preview image for all .rtdc files

    This also happens for draft datasets.
    """
    # go through all datasets
    datasets = model.Session.query(model.Package)
    nl = False  # new line character
    for dataset in datasets:
        nl = False
        click.echo(f"Checking dataset {dataset.id}\r", nl=False)
        for resource in dataset.resources:
            res_dict = resource.as_dict()
            try:
                if jobs.generate_condensed_resource_job(res_dict,
                                                        override=False):
                    click_echo(
                        f"Created condensed resource for {resource.name}", nl)
                    nl = True
            except KeyboardInterrupt:
                raise
            except BaseException as e:
                click_echo(
                    f"{e.__class__.__name__}: {e} for {res_dict['name']}", nl)
                nl = True
    if not nl:
        click.echo("")
    click.echo("Done!")


def get_commands():
    return [run_jobs_dc_view]
