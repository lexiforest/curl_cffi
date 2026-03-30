Options
=======

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
    curl-cffi get --headers https://httpbin.org/get

    # Body only (no headers)
    curl-cffi get --body https://httpbin.org/get

    # Full verbose output
    curl-cffi post -v https://httpbin.org/post name=test

    # Custom: request headers + response headers
    curl-cffi get -p Hh https://httpbin.org/get

Download
--------

Downloads display a progress bar with transfer speed. Filenames are
automatically sanitized to remove unsafe characters.

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
    curl-cffi get --download https://example.com/file.zip

    # Download to a specific path
    curl-cffi get --download -o myfile.zip https://example.com/file.zip

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
    curl-cffi get -a user:password https://httpbin.org/basic-auth/user/password

    # Skip SSL verification
    curl-cffi get --no-verify https://self-signed.example.com

    # Use a proxy
    curl-cffi get --proxy http://proxy:8080 https://httpbin.org/get

    # Set timeout
    curl-cffi get --timeout 5 https://httpbin.org/delay/3

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
    curl-cffi get https://tls.browserleaks.com/json

    # Impersonate Safari
    curl-cffi get -i safari https://tls.browserleaks.com/json

    # Impersonate Firefox
    curl-cffi get -i firefox https://tls.browserleaks.com/json
