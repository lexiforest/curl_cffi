CLI
***

``curl-cffi`` ships with a friendly command-line interface for making HTTP
requests with browser impersonation.

Install
=======

The CLI is included when you install ``curl_cffi``:

.. code-block:: bash

    pip install curl_cffi

Install the optional ``cli`` extra for syntax highlighting and download progress
bars:

.. code-block:: bash

    pip install 'curl_cffi[cli]'

On macOS, you can also install via Homebrew:

.. code-block:: bash

    brew install lexiforest/tap/curl-cffi

The command ``curl-cffi`` will be available in your shell. If it's not in your ``PATH``
for some reason, you can:

1. Add it to your ``PATH``
2. Try something like ``uv run curl-cffi`` or ``python -m curl_cffi``

Usage
=====

.. code-block:: text

    curl-cffi METHOD URL [REQUEST_ITEMS...] [FLAGS]

- **METHOD** is required. Use ``get``, ``post``, ``put``, ``delete``, ``patch``,
  ``head``, ``options``, ``trace``, or ``query`` (case-insensitive).
- **URL** is required. Bare domains default to ``https://`` (e.g.
  ``example.com`` becomes ``https://example.com``). A leading colon is a
  localhost shortcut (e.g. ``:3000`` becomes ``http://localhost:3000``).
  When an explicit port other than 443 is given, ``http://`` is used instead
  (e.g. ``example.com:8080`` becomes ``http://example.com:8080``).
- **REQUEST_ITEMS** use special separators to specify headers, query
  parameters, body fields, and cookies (see :doc:`request_items`).

Quick examples
--------------

.. code-block:: bash

    # Simple GET
    curl-cffi get https://httpbin.org/get

    # GET with a custom header
    curl-cffi get https://httpbin.org/get X-My-Header:value

    # POST JSON, `:=` means interpret the value instead of string
    curl-cffi post https://httpbin.org/post name=John age:=30

    # POST form data
    curl-cffi post --form https://httpbin.org/post name=John

    # Verbose output (request + response headers and body)
    curl-cffi get -v https://httpbin.org/get

    # Impersonate chrome by default
    curl-cffi get tls.browserleaks.com/json

    # Impersonate Safari instead of Chrome
    curl-cffi get -i safari tls.browserleaks.com/json

    # http3
    curl-cffi get --http3 https://fp.impersonate.pro/api/http3

    # Localhost shortcut
    curl-cffi get :8000/api/health

.. toctree::
   :maxdepth: 2
   :caption: Documentation:

   request_params
   options
   run
   doctor
   pro
   vs_others
