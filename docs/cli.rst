CLI
***

``curl-cffi`` ships with an HTTPie-style command-line interface for making HTTP
requests with browser impersonation.

Install
=======

The CLI is included when you install ``curl_cffi``:

.. code-block:: bash

    pip install curl_cffi

The command ``curl-cffi`` will be available in your shell.

Usage
=====

.. code-block:: text

    curl-cffi [FLAGS] [METHOD] URL [REQUEST_ITEMS...]

- **METHOD** is optional. If omitted, ``GET`` is used when there is no request
  body, ``POST`` when data fields are present.
- **URL** is required. Bare domains default to ``https://`` (e.g.
  ``example.com`` becomes ``https://example.com``). A leading colon is a
  localhost shortcut (e.g. ``:3000`` becomes ``http://localhost:3000``).
- **REQUEST_ITEMS** use special separators to specify headers, query
  parameters, and body fields (see below).

Quick examples
--------------

.. code-block:: bash

    # Simple GET (default method)
    curl-cffi https://httpbin.org/get

    # Explicit GET with a custom header
    curl-cffi GET https://httpbin.org/get X-My-Header:value

    # POST JSON (auto-detected because of data fields)
    curl-cffi https://httpbin.org/post name=John age:=30

    # POST form data
    curl-cffi --form https://httpbin.org/post name=John

    # Verbose output (request + response headers and body)
    curl-cffi -v https://httpbin.org/get

    # Impersonate Safari instead of Chrome
    curl-cffi -i safari https://httpbin.org/get

    # Localhost shortcut
    curl-cffi :8000/api/health

Request Items
=============

Request items are positional arguments after the URL. The separator determines
how each item is interpreted:

.. list-table::
   :widths: 20 30 50
   :header-rows: 1

   * - Separator
     - Type
     - Example
   * - ``Header:Value``
     - HTTP header
     - ``Content-Type:application/json``
   * - ``Header:``
     - Header removal (empty value)
     - ``Accept:``
   * - ``param==value``
     - Query parameter
     - ``page==2``
   * - ``field=value``
     - Data field (string)
     - ``name=John``
   * - ``field:=json``
     - Raw JSON field
     - ``age:=30`` ``tags:=["a","b"]``
   * - ``@filepath``
     - File upload
     - ``@photo.jpg``

Content type
------------

By default, data fields are serialized as JSON. Use flags to change this:

.. code-block:: bash

    # JSON (default)
    curl-cffi https://httpbin.org/post name=test count:=5

    # Form-encoded
    curl-cffi --form https://httpbin.org/post name=test

    # Multipart
    curl-cffi --multipart https://httpbin.org/post name=test @file.txt

Flags
=====

Content type flags
------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Flag
     - Description
   * - ``--json``, ``-j``
     - Serialize data items as JSON (default)
   * - ``--form``, ``-f``
     - Serialize data items as form fields
   * - ``--multipart``
     - Force multipart form data

Output control
--------------

When connected to a terminal, the default output includes response headers and
body with syntax highlighting (JSON, HTML, XML). When piped, only the body is
printed as plain text.

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Flag
     - Description
   * - ``--verbose``, ``-v``
     - Print request headers, request body, response headers, and response body
   * - ``--headers``
     - Print response headers only
   * - ``--body``, ``-b``
     - Print response body only
   * - ``--print``, ``-p``
     - Fine-grained control using a string of characters:
       ``H`` (request headers), ``B`` (request body),
       ``h`` (response headers), ``b`` (response body).
       Example: ``--print=Hh`` for headers only.

.. code-block:: bash

    # Headers only
    curl-cffi --headers https://httpbin.org/get

    # Body only (no headers)
    curl-cffi --body https://httpbin.org/get

    # Full verbose output
    curl-cffi -v POST https://httpbin.org/post name=test

    # Custom: request headers + response headers
    curl-cffi -p Hh https://httpbin.org/get

Download
--------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Flag
     - Description
   * - ``--download``, ``-d``
     - Download response body to a file (filename from ``Content-Disposition``
       header or URL path)
   * - ``--output``, ``-o``
     - Specify output file path

.. code-block:: bash

    # Download a file
    curl-cffi --download https://example.com/file.zip

    # Download to a specific path
    curl-cffi --download -o myfile.zip https://example.com/file.zip

Connection options
------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Flag
     - Description
   * - ``--auth``, ``-a``
     - HTTP authentication (``user:password``)
   * - ``--verify`` / ``--no-verify``
     - Enable/disable SSL certificate verification (default: enabled)
   * - ``--proxy``
     - Proxy URL
   * - ``--timeout``
     - Request timeout in seconds
   * - ``--follow`` / ``--no-follow``
     - Follow/don't follow redirects (default: follow)
   * - ``--max-redirects``
     - Maximum number of redirects (default: 30)

.. code-block:: bash

    # Basic auth
    curl-cffi -a user:password https://httpbin.org/basic-auth/user/password

    # Skip SSL verification
    curl-cffi --no-verify https://self-signed.example.com

    # Use a proxy
    curl-cffi --proxy http://proxy:8080 https://httpbin.org/get

    # Set timeout
    curl-cffi --timeout 5 https://httpbin.org/delay/3

Browser impersonation
---------------------

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Flag
     - Description
   * - ``--impersonate``, ``-i``
     - Browser to impersonate (default: ``chrome``)

.. code-block:: bash

    # Impersonate Chrome (default)
    curl-cffi https://tls.browserleaks.com/json

    # Impersonate Safari
    curl-cffi -i safari https://tls.browserleaks.com/json

    # Impersonate Firefox
    curl-cffi -i firefox https://tls.browserleaks.com/json

Doctor
======

The ``doctor`` subcommand prints diagnostic information useful for debugging:

.. code-block:: bash

    curl-cffi doctor

Example output:

.. code-block:: text

    curl-cffi doctor
    ----------------
    python: 3.10.20
    executable: /usr/bin/python3
    platform: macOS-15.4-arm64-arm-64bit
    machine: arm64
    curl_cffi: 0.15.0b4
    libcurl: libcurl/8.12.1
