Batch Execution
===============

The ``run`` subcommand executes requests from a file. It auto-detects the
format by file extension.

.. code-block:: bash

    curl-cffi run requests.http
    curl-cffi run session.har

Supported formats:

- ``.http`` / ``.rest`` -- HTTP Request in Editor format (`spec <https://github.com/JetBrains/http-request-in-editor-spec/blob/master/spec.md>`_)
- ``.har`` -- HAR (HTTP Archive) format

HTTP files
----------

The HTTP Request in Editor format lets you define multiple requests in a single
file, separated by ``###``.

.. code-block:: text

    ### Get user list
    GET https://api.example.com/users

    ### Create a user
    POST https://api.example.com/users
    Content-Type: application/json

    {"name": "Alice", "email": "alice@example.com"}

    ### Get a specific user
    GET https://api.example.com/users/1

Features:

- Requests separated by ``###`` (with optional comment text after)
- Request line: ``[METHOD] URL [HTTP/version]`` (method defaults to ``GET``)
- Headers follow the request line immediately
- Body after a blank line
- Comments with ``#`` or ``//``
- File references with ``< filepath`` to include body from a file

.. code-block:: text

    POST https://api.example.com/upload
    Content-Type: application/json

    < body.json

HAR files
---------

HAR (HTTP Archive) files can be exported from browser DevTools. The ``run``
command replays all entries in the archive.

.. code-block:: bash

    curl-cffi run captured.har

.. note::

    Chrome exported HAR files do not contain cookies and auth headers by
    default. To include them, go to DevTools settings: Gear Icon > Preferences
    > Network > select "Allow to generate HAR with sensitive data".

Session
-------

By default, all requests in a batch share a single session, so cookies and
connections persist across requests. To disable this and execute each request
independently, use ``--no-session``:

.. code-block:: bash

    # Default: shared session (cookies carry over between requests)
    curl-cffi run requests.http

    # Independent requests (no shared state)
    curl-cffi run --no-session requests.http

Error handling
--------------

When running multiple requests, execution continues even if individual requests
fail. A summary of failures is printed at the end:

.. code-block:: text

    --- [1] GET https://api.example.com/users
    --- [2] POST https://api.example.com/missing
    --- [3] GET https://api.example.com/health

    1 request(s) failed.
