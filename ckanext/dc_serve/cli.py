import datetime
import time

import ckan.model as model

import click


from . import jobs


def click_echo(message, am_on_a_new_line):
    if not am_on_a_new_line:
        click.echo("")
    click.echo(message)


@click.option('--modified-days', default=-1,
              help='Only run for datasets modified within this number of days '
                   + 'in the past. Set to -1 to apply to all datasets.')
@click.command()
def run_jobs_dc_serve(modified_days=-1):
    """Compute condensed resource all .rtdc files

    This also happens for draft datasets.
    """
    # go through all datasets
    datasets = model.Session.query(model.Package)

    if modified_days >= 0:
        # Search only the last `days` days.
        past = datetime.date.today() - datetime.timedelta(days=modified_days)
        past_str = time.strftime("%Y-%m-%d", past.timetuple())
        datasets = datasets.filter(model.Package.metadata_modified >= past_str)

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
    return [run_jobs_dc_serve]
