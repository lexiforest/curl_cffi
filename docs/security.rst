Security
========

SSRF protection
---------------

Server-Side Request Forgery (SSRF) is an attack where an attacker can induce a
server-side application to make HTTP requests to an unintended destination. A
common vector is **open redirects**: a request to a public URL returns a ``3xx``
redirect pointing to an internal or private IP address (e.g. ``127.0.0.1``,
``10.x.x.x``, ``169.254.169.254``). If the client blindly follows the redirect,
the attacker gains access to internal services.

By default, ``curl_cffi`` follows redirects (``allow_redirects=True``) without
restricting the target, which mirrors the behavior of ``requests`` and ``httpx``.
This is fine for desktop applications and scripts, but **dangerous in
server-side contexts** where user-supplied URLs are fetched.

Example: vulnerable FastAPI app
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Consider a preview service that fetches a URL on behalf of the user:

.. code-block:: python

    from fastapi import FastAPI
    from curl_cffi import requests

    app = FastAPI()

    @app.get("/preview")
    def preview(url: str):
        # VULNERABLE: follows redirects to any destination
        r = requests.get(url)
        return {"body": r.text}

An attacker can exploit this by supplying a URL that redirects to an internal
service:

.. code-block:: text

    GET /preview?url=https://evil.com/redirect

Where ``https://evil.com/redirect`` returns:

.. code-block:: text

    HTTP/1.1 302 Found
    Location: http://169.254.169.254/latest/meta-data/iam/security-credentials/

The application follows the redirect and returns AWS instance credentials (or
any other internal resource) to the attacker.

The fix is to use ``CurlFollow.SAFE``:

.. code-block:: python

    from fastapi import FastAPI
    from curl_cffi import CurlFollow, requests

    app = FastAPI()

    @app.get("/preview")
    def preview(url: str):
        # SAFE: rejects redirects to internal/private IPs
        r = requests.get(url, allow_redirects=CurlFollow.SAFE)
        return {"body": r.text}

Using ``CurlFollow.SAFE``
^^^^^^^^^^^^^^^^^^^^^^^^^

``curl_cffi`` exposes a ``CurlFollow.SAFE`` option backed by
``curl-impersonate`` that rejects redirects to internal/private IP addresses:

.. code-block:: python

    from curl_cffi import CurlFollow, requests

    # Recommended for server-side code that fetches user-supplied URLs
    r = requests.get(url, allow_redirects=CurlFollow.SAFE)

    # The string "safe" is also accepted
    r = requests.get(url, allow_redirects="safe")

    # Session-level setting
    s = requests.Session(allow_redirects=CurlFollow.SAFE)

With ``CurlFollow.SAFE``, redirects to the following address ranges are
rejected:

- Loopback (``127.0.0.0/8``, ``::1``)
- Private networks (``10.0.0.0/8``, ``172.16.0.0/12``, ``192.168.0.0/16``)
- Link-local (``169.254.0.0/16``, ``fe80::/10``)

``allow_redirects`` values
^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Value
     - Behavior
   * - ``True`` (default)
     - Follow all redirects (same as ``CurlFollow.ALL``)
   * - ``False``
     - Do not follow any redirects
   * - ``CurlFollow.SAFE`` or ``"safe"``
     - Follow redirects, but reject redirects to internal/private IPs
   * - ``CurlFollow.ALL``
     - Follow all redirects
   * - ``CurlFollow.OBEYCODE``
     - Follow redirects, reset custom method on 301/302/303
   * - ``CurlFollow.FIRSTONLY``
     - Only use custom method for the first request, reset for subsequent
       redirects

Recommendation
^^^^^^^^^^^^^^

If your application fetches URLs provided by users or external systems, always
use ``CurlFollow.SAFE``:

.. code-block:: python

    from curl_cffi import CurlFollow, requests

    session = requests.Session(allow_redirects=CurlFollow.SAFE)

This protects against SSRF without disabling redirects entirely.
