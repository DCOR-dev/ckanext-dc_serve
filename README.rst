ckanext-dc_serve
================

This CKAN plugin provides an API for accessing DC data. The python
package dclab implements a client library (``dclab.rtdc_dataset.fmt_dcor``)
to access this API. Shape-Out 2 offers a GUI via *File - Load DCOR data*.

This plugin implements:

- The DCOR API for accessing DC datasets online.
- A background job that generates a condensed dataset after a resource
  has been created.
- A route that makes the condensed dataset available via
  "/dataset/{id}/resource/{resource_id}/condensed.rtdc"


Installation
------------

::

    pip install ckanext-dc_serve


Add this extension to the plugins and defaul_views in ckan.ini:

::

    ckan.plugins = [...] dc_serve
