ckanext-dc_serve
================

|PyPI Version| |Build Status| |Coverage Status|

This CKAN plugin provides an API for accessing DC data. The python
package dclab implements a client library (``dclab.rtdc_dataset.fmt_dcor``)
to access this API. Shape-Out 2 offers a GUI via *File - Load DCOR data*.

This plugin implements:

- The DCOR API for accessing DC datasets online.
- A background job that generates a condensed dataset after a resource
  has been created.
- A route that makes the condensed dataset available via
  "/dataset/{id}/resource/{resource_id}/condensed.rtdc"
- Extends the template to show a condensed resource download button

- CLI:

  - add CKAN command `run-jobs-dc-serve` that runs all background
    jobs for all resources (if not already done)


Installation
------------

::

    pip install ckanext-dc_serve


Add this extension to the plugins and defaul_views in ckan.ini:

::

    ckan.plugins = [...] dc_serve


Testing
-------
If CKAN/DCOR is installed and setup for testing, this extension can
be tested with pytest:

::

    pytest ckanext

Testing can also be done via vagrant in a virtualmachine using the
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
.. |Build Status| image:: https://img.shields.io/github/workflow/status/DCOR-dev/ckanext-dc_serve/Checks
   :target: https://github.com/DCOR-dev/ckanext-dc_serve/actions?query=workflow%3AChecks
.. |Coverage Status| image:: https://img.shields.io/codecov/c/github/DCOR-dev/ckanext-dc_serve
   :target: https://codecov.io/gh/DCOR-dev/ckanext-dc_serve
