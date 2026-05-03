curl-cffi vs curl-impersonate vs HTTPie
=======================================

Why do we need yet another http request tool?

Quick comparison
----------------

.. list-table::
   :widths: 30 23 23 24
   :header-rows: 1

   * -
     - curl-cffi
     - curl-impersonate
     - HTTPie
   * - Browser impersonation
     - Yes
     - Yes
     - No
   * - HTTP/2
     - Yes
     - Yes
     - No
   * - HTTP/3
     - Yes
     - Yes
     - No
   * - Easier options
     - Yes
     - No
     - Yes
   * - Syntax highlighting
     - Yes
     - No
     - Yes
   * - Batch execution
     - Yes
     - No
     - No

.. note::

    Compared to ``curl-impersonate``, ``curl-cffi`` CLI does not expose all impersonate
    options in current version, but that is to be updated soon.

curl-cffi vs curl-impersonate
-----------------------------

curl is the swiss army knife of HTTP, but its syntax can be intimidating for beginners:

.. code-block:: bash

    # curl
    curl -X POST https://api.example.com/users \
      -H "Content-Type: application/json" \
      -d '{"name": "Alice", "age": 30}'

    # curl-cffi
    curl-cffi post https://api.example.com/users name=Alice age:=30

curl-cffi uses a more readable syntax with request items (``key=value``,
``key:=json``, ``Header:Value``) instead of flags like ``-H`` and ``-d``.

That said, if you are already comfortable with curl syntax, you can use
`curl-impersonate <https://github.com/lexiforest/curl-impersonate>`_ directly
for browser impersonation with familiar flags.

curl-cffi vs HTTPie
-------------------

Syntax
^^^^^^

HTTPie has a friendly CLI syntax for HTTP requests, and ``curl-cffi`` shares many of
its ideas. However, there are some key differences:

**Explicit methods.** curl-cffi requires the HTTP method as a subcommand, while
HTTPie guesses it based on whether data is present:

.. code-block:: bash

    # HTTPie -- implicit POST because of data fields
    http example.com/api name=test

    # curl-cffi -- method is always explicit
    curl-cffi post example.com/api name=test

This explicitness is intentional. It follows the Python philosophy of "explicit
is better than implicit", and it makes curl-cffi commands unambiguous when used
by AI agents or in scripts, where guessing intent from context is unreliable.

HTTP/2 and HTTP/3
^^^^^^^^^^^^^^^^^

HTTPie only supports HTTP/1.1. curl-cffi supports HTTP/2 and HTTP/3 out of the box,
which is critical for browser impersonation and for testing modern APIs.

Browser impersonation
^^^^^^^^^^^^^^^^^^^^^

curl-cffi can impersonate browsers' TLS fingerprints, which HTTPie cannot do.


Batch execution
---------------

``curl-cffi`` has a builtin ``run`` command that can execute multiple requests from a
single file, supporting both ``.http`` and ``.har`` formats.

**.http files** -- define multiple requests in a human-readable format, separated by
``###``. Supported by JetBrains IDEs and VS Code REST Client:

.. code-block:: text

    ### Get users
    GET https://api.example.com/users

    ### Create user
    POST https://api.example.com/users
    Content-Type: application/json

    {"name": "Alice"}

.. code-block:: bash

    curl-cffi run requests.http

**.har files** -- replay HTTP traffic exported from Chrome DevTools. This is especially
useful for reproducing real-world requests, including headers, cookies, and POST bodies:

.. code-block:: bash

    curl-cffi run session.har

Neither curl nor HTTPie supports batch execution natively. With curl you would need a
shell loop or ``xargs``; with HTTPie you would need a wrapper script. ``curl-cffi run``
handles sequencing, error reporting, and a summary of failures out of the box.

See :doc:`run` for full details on supported file formats and options.


When to use which
-----------------

- **curl-cffi** -- when you need browser impersonation, HTTP/2/3 support, or a
  CLI that works well with AI agents and scripts.
- **curl / curl-impersonate** -- when you are already fluent in curl syntax and
  want the full power of libcurl.
- **HTTPie** -- when you only need HTTP/1.1 and prefer implicit method
  detection.
