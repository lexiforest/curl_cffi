Advanced Topics
**************

Proxies
=======

You can use the ``proxy`` parameter:

.. code-block:: python

    import curl_cffi

    curl_cffi.get(url, proxy="http://user:pass@example.com:3128")

You can also use the ``http_proxy``, ``https_proxy``, and ``ws_proxy``, ``wss_proxy``
environment variables, respectively.

.. warning::

   For beginners, a very common mistake is to add ``https://`` prefix to the ``https`` proxy.

   For explanation of differences between ``http_proxy`` and ``https_proxy``, please see
   `#6 <https://github.com/lexiforest/curl_cffi/issues/6>`_.

For compatibility with ``requests``, we also support using dicts.

.. code-block:: python

    import curl_cffi

    proxies = {
        "http": "http://localhost:3128",
        "https": "http://localhost:3128"
    }
    curl_cffi.get(url, proxies=proxies)


.. note::

   Prefer the single `proxy` parameter, unless you do have different proxies for http and https


Response cache
==============

``Session`` can cache successful responses on disk. This is especially useful for
tests and local mocks: the first request records a real response, and later
requests with the same method, URL and request body are served from the cache.

The simplest form is to pass a number of seconds or a ``timedelta``:

.. code-block:: python

    from datetime import timedelta
    from curl_cffi import Session

    with Session(cache=timedelta(minutes=10)) as s:
        first = s.get("https://example.com/api/users")
        second = s.get("https://example.com/api/users")  # served from cache

By default, cached files are stored in a ``curl_cffi_cache`` directory under the
system temporary directory. Use ``FileCacheBackend`` when you want a stable cache
directory, for example inside a test fixture:

.. code-block:: python

    from datetime import timedelta
    from curl_cffi import FileCacheBackend, Session

    cache = FileCacheBackend(
        path="tests/.cache/http",
        expires=timedelta(hours=1),
    )

    with Session(cache=cache) as s:
        response = s.get("https://api.example.test/items")

Only successful responses are stored by default. Cached responses preserve the
response body, status code, headers, cookies and common curl metadata. On a cache
hit, response cookies are also merged into the session cookie jar, matching normal
``Session`` behavior.

Ignoring query parameters
-------------------------

You can ignore volatile query parameters when building cache keys. This is useful
for analytics, cache-busting or nonce parameters that should not create separate
cache entries.

.. code-block:: python

    from datetime import timedelta
    from curl_cffi import FileCacheBackend, Session

    cache = FileCacheBackend(
        expires=timedelta(minutes=10),
        ignored=["utm_source", "cache_buster"],
    )

    with Session(cache=cache) as s:
        s.get("https://example.com/items?item=1&utm_source=a")
        s.get("https://example.com/items?item=1&utm_source=b")  # same cache entry


Clearing cache files
--------------------

Call ``clear`` to remove cache entries managed by that backend:

.. code-block:: python

    cache.clear()

``FileCacheBackend.clear`` only removes cache-looking files from its own cache
directory.


Custom backends
---------------

To store responses somewhere other than the filesystem, subclass
``CacheBackend`` and implement the storage methods:

.. code-block:: python

    from datetime import timedelta
    from curl_cffi import CacheBackend, Session

    class DictCache(CacheBackend):
        def __init__(self):
            super().__init__(expires=timedelta(minutes=10))
            self.data = {}

        def _read_payload(self, key):
            return self.data.get(key)

        def _write_payload(self, key, payload):
            self.data[key] = payload

        def _delete_payload(self, key):
            self.data.pop(key, None)

        def clear(self):
            self.data.clear()

    with Session(cache=DictCache()) as s:
        response = s.get("https://example.com/api")


Limitations
-----------

- The built-in cache currently works with synchronous ``Session`` only.
  ``AsyncSession`` rejects the ``cache`` option because the backend API is
  blocking.
- Streamed responses and requests using ``content_callback`` are not cached.
- The default key uses request method, normalized URL and request body. Be careful
  with authenticated or cookie-specific responses; use a custom backend or a
  separate cache directory when different users may receive different content for
  the same URL.


Low-level curl API
=========

Although we provide an easy to use ``requests``-like API, sometimes, you may prefer to use the ``curl``-like API.

The curl API is very much like what you may have used -- ``pycurl``, with extra impersonation support.


.. code-block:: python

    from curl_cffi import Curl, CurlOpt
    from io import BytesIO

    buffer = BytesIO()
    c = Curl()
    c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
    c.setopt(CurlOpt.WRITEDATA, buffer)

    c.impersonate("chrome124")

    c.perform()
    c.close()
    body = buffer.getvalue()
    print(body.decode())

For a complete list of options, see :doc:`api`


Using ``CURLOPT_*`` in requests API
===================================

Sometimes, you know an option from libcurl, but we haven't exposed it in the requests API.
You can simply add the ``curl_options`` dict to apply the option.

.. code-block:: python


.. note::

   Using curl_options is preferred over using ``session.curl.setopt``, the latter may get
   overriden internally, while the former is executed after all options have been set.


Selecting http version
======================

The recommended and default http version is http/2, the present and most widely used http version
as of 2025.

According to `Wikipedia <https://en.wikipedia.org/wiki/HTTP>`_, the marketshare is:

- HTTP/1.1, 33.8%
- HTTP/2, 35.3%
- HTTP/3, 30.9%

To change http versions, use the ``http_version`` parameter.

.. code-block:: python

   import curl_cffi
   curl_cffi.get("https://cloudflare-quic.com", http_version="v3")

Common values are: ``v1``, ``v2``, ``v3`` and ``v3only``.

To get the actual used http version, you need to compare the response field with const from libcurl:

.. code-block:: python

    >>> from curl_cffi import CurlHttpVersion
    >>> r = curl_cffi.get("https://example.com", http_version="v2")
    >>> r.http_version == CurlHttpVersion.V2_0
    True


Keeping session alive in http/2
======

With http/2, you can optionally send a ping frame to keep the connection alive when not actively using it.


.. code-block:: python

   import curl_cffi

   s = Session()
   s.get("https://example.com")
   s.upkeep()
