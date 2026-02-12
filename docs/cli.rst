curl-cffi CLI
*************

``curl_cffi`` ships with a command line interface named ``curl-cffi``.


Usage
=====

Show top-level help:

.. code-block:: sh

    curl-cffi --help

Fetch URLs
==========

Use the ``fetch`` command to request one or more URLs. This is handy we you want to
verify if a website can be accessed.

.. code-block:: sh

    curl-cffi fetch https://example.com
    curl-cffi fetch -i chrome https://tls.browserleaks.com/json
    curl-cffi fetch -i safari https://example.com https://httpbin.org/get

Options:

- ``-i, --impersonate``: browser target, defaults to ``chrome``.

Update and list local fingerprints
==================================

Download the latest fingerprints:

.. code-block:: sh

    curl-cffi update

List cached fingerprints:

.. code-block:: sh

    curl-cffi list

Configure API key
=================

Store your impersonate.pro API key:

.. code-block:: sh

    curl-cffi config --api-key imp_xxxxxxxx

Diagnostics
===========

Run ``doctor`` when reporting issues:

.. code-block:: sh

    curl-cffi doctor

It prints Python, platform, libcurl, API root, and local fingerprint cache paths.

Environment variables
=====================

- ``IMPERSONATE_API_ROOT``: override API endpoint used by ``update``.
- ``IMPERSONATE_CONFIG_DIR``: override local config/cache directory.
