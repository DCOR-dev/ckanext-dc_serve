""" Testing background jobs

Due to the asynchronous nature of background jobs, code that uses them needs
to be handled specially when writing tests.

A common approach is to use the mock package to replace the
ckan.plugins.toolkit.enqueue_job function with a mock that executes jobs
synchronously instead of asynchronously
"""
import mock
import pathlib

import pytest

import ckan.lib
import ckan.tests.factories as factories

import dcor_shared

from .helper_methods import make_dataset


data_dir = pathlib.Path(__file__).parent / "data"


def synchronous_enqueue_job(job_func, args=None, kwargs=None, title=None,
                            queue=None, rq_kwargs=None):
    """
    Synchronous mock for ``ckan.plugins.toolkit.enqueue_job``.
    """
    if rq_kwargs is None:
        rq_kwargs = {}
    args = args or []
    kwargs = kwargs or {}
    job_func(*args, **kwargs)


# We need the dcor_depot extension to make sure that the symbolic-
# linking pipeline is used.
@pytest.mark.ckan_config('ckan.plugins', 'dcor_depot dc_serve dcor_schemas')
@pytest.mark.usefixtures('clean_db', 'with_request_context')
@mock.patch('ckan.plugins.toolkit.enqueue_job',
            side_effect=synchronous_enqueue_job)
def test_create_condensed_dataset_job(enqueue_job_mock, create_with_upload,
                                      monkeypatch, ckan_config, tmpdir):
    monkeypatch.setitem(ckan_config, 'ckan.storage_path', str(tmpdir))
    monkeypatch.setattr(ckan.lib.uploader, '_storage_path', str(tmpdir))

    user = factories.User()
    owner_org = factories.Organization(users=[{
        'name': user['id'],
        'capacity': 'admin'
    }])
    # Note: `call_action` bypasses authorization!
    # create 1st dataset
    create_context = {'ignore_auth': False, 'user': user['name'],
                      'api_version': 3}
    dataset = make_dataset(create_context, owner_org, with_resource=False,
                           activate=False)
    content = (data_dir / "calibration_beads_47.rtdc").read_bytes()
    result = create_with_upload(
        content, 'test.rtdc',
        url="upload",
        package_id=dataset["id"],
        context=create_context,
    )
    path = dcor_shared.get_resource_path(result["id"])
    cond = path.with_name(path.name + "_condensed.rtdc")
    # existence of original uploaded file
    assert path.exists()
    # existence of condensed file
    assert cond.exists()
