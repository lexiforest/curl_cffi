Request Parameters
==================

Request parameters are positional arguments after the URL.

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
     - JSON/form field (as string)
     - ``name=John``
   * - ``field:=json``
     - JSON field (interpreted)
     - ``age:=30`` ``tags:=["a","b"]``
   * - ``@filepath``
     - File upload
     - ``@photo.jpg``
   * - ``+key=value``
     - Cookie
     - ``+session=abc123``

Content type
------------

By default, data fields are serialized as JSON. Use flags to change this:

.. code-block:: bash

    # JSON (default)
    curl-cffi post https://httpbin.org/post name=test count:=5

    # Form-encoded
    curl-cffi post --form https://httpbin.org/post name=test

    # Multipart
    curl-cffi post --multipart https://httpbin.org/post name=test @file.txt

Cookies
-------

Use the ``+`` separator to set cookies on the request:

.. code-block:: bash

    # Set a single cookie
    curl-cffi get https://httpbin.org/cookies +session=abc123

    # Set multiple cookies
    curl-cffi get https://httpbin.org/cookies +session=abc123 +theme=dark
