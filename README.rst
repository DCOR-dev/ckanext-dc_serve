ckanext-dc_serve
================

|PyPI Version| |Build Status| |Coverage Status|

This CKAN plugin provides an API for accessing DC data. The python
package dclab implements a client library (``dclab.rtdc_dataset.fmt_dcor``)
to access this API. Shape-Out 2 offers a GUI via *File - Load DCOR data*.

This plugin implements:

- The DCOR API for accessing DC datasets online (dcserv).
- A background job that generates a condensed dataset after a resource
  has been created.
- A background job that uploads the condensed dataset to the S3 object
  store. The temporary location of the condensed dataset that is created
  can be set by setting the `ckanext.dc_serve.tmp_dir` configuration
  option.
- A route that makes the condensed dataset available via
  "/dataset/{id}/resource/{resource_id}/condensed.rtdc"
  (S3 object store data is made available via a redirect)
- A route overriding the default route for downloading a resource via
  "/dataset/{id}/resource/{resource_id}/download/resource_name"
  (S3 object store data is made available via a redirect)
- Extends the template to show a condensed resource download button

- CLI:

  - add CKAN command `run-jobs-dc-serve` that runs all background
    jobs for all resources (if not already done)

- Configuration keywords:

  - the ``ckanext.dc_serve.create_condensed_datasets`` boolean
    parameter can be set to False to prevent DCOR from generating condensed
    resource files

  - ``ckanext.dc_serve.tmp_dir`` specifies the location of a directory
    used for creating temporary files when condensing datasets; if not
    specified, a temporary directory is used



Installation
------------

::

    pip install ckanext-dc_serve


Add this extension to the plugins and defaul_views in ckan.ini:

::

    ckan.plugins = [...] dc_serve


Testing
-------
Testing is done via vagrant in a virtualmachine using the
`dcor-test <https://app.vagrantup.com/paulmueller/boxes/dcor-test/>` image.
Make sure that `vagrant` and `virtualbox` are installed and run the
following commands in the root of this repository:

::

    # Setup virtual machine using `Vagrantfile`
    vagrant up
    # Run the tests
    vagrant ssh -- sudo bash /testing/vagrant-run-tests.sh


.. |PyPI Version| image:: https://img.shields.io/pypi/v/ckanext.dc_serve.svg
   :target: https://pypi.python.org/pypi/ckanext.dc_serve
.. |Build Status| image:: https://img.shields.io/github/actions/workflow/status/DCOR-dev/ckanext-dc_serve/check.yml
   :target: https://github.com/DCOR-dev/ckanext-dc_serve/actions?query=workflow%3AChecks
.. |Coverage Status| image:: https://img.shields.io/codecov/c/github/DCOR-dev/ckanext-dc_serve
   :target: https://codecov.io/gh/DCOR-dev/ckanext-dc_serve
