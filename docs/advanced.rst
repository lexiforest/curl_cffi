Advanced Topics
**************

DNS servers
===========

Use ``dns`` to select a DNS server or a list of servers instead of the system
resolver. This requires libcurl to be built with c-ares; it is unavailable in
builds that use a threaded or system resolver. ``AsyncSession`` accepts the same
session-level and request-level ``dns`` option.

.. code-block:: python

    from curl_cffi import Session

    with Session(dns=["8.8.8.8", "8.8.4.4"]) as session:
        response = session.get("https://example.com")
        response = session.get("https://example.com", dns="1.1.1.1")

An empty string or list uses the system resolver. Server addresses may include a port,
for example ``"8.8.8.8:5353"``.

This option can boost your performance, according to some users who have already used
this before.

Proxies
=======

You can use the ``proxy`` parameter:

.. code-block:: python

    import curl_cffi

    curl_cffi.get(url, proxy="http://user:pass@example.com:3128")

You can also use the ``http_proxy``, ``https_proxy``, and ``ws_proxy``, ``wss_proxy``
environment variables, respectively.

For HTTP requests, set ``trust_env=False`` on ``Session`` or ``AsyncSession``
to ignore proxy environment variables:

.. code-block:: python

    from curl_cffi import Session

    with Session(trust_env=False) as session:
        response = session.get("https://example.com")

Explicit ``proxy=`` and ``proxies=`` settings still apply. With
``trust_env=False``, ``no_proxy`` also cannot bypass an explicit proxy.

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

HTTP/3 over proxies
-------------------

With ``http_version="v3"`` or ``"v3only"``, a ``socks5://`` proxy carries QUIC via UDP
ASSOCIATE, and an ``https://`` proxy via MASQUE CONNECT-UDP.

To talk HTTP/3 to the proxy itself, set its type to ``CurlProxyType.HTTPS3``:

.. code-block:: python

    import curl_cffi
    from curl_cffi import CurlOpt, CurlProxyType

    curl_cffi.get(
        url,
        proxy="https://proxy.example.com:443",
        http_version="v3only",
        curl_options={CurlOpt.PROXYTYPE: CurlProxyType.HTTPS3},
    )


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

When the session creates the backend from a duration, access it through the
read-only ``cache_backend`` property:

.. code-block:: python

    from curl_cffi import Session

    with Session(cache=600) as session:
        response = session.get("https://example.com")
        session.cache_backend.clear()

``cache_backend`` is ``None`` when response caching is disabled. This cache stores
HTTP responses; ``CurlShare`` shares DNS and TLS session data separately.


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

    from curl_cffi import CurlHttpVersion, CurlOpt, requests

    response = requests.get(
        "https://example.com",
        curl_options={CurlOpt.HTTP_VERSION: CurlHttpVersion.V1_1},
    )


.. note::

   Using curl_options is preferred over using ``session.curl.setopt``, the latter may get
   overriden internally, while the former is executed after all options have been set.


.. _ssl-context-callbacks:

SSL context callbacks and certificate distrust
==============================================

.. versionadded:: 0.17.0b1

``CurlOpt.SSL_CTX_FUNCTION`` accepts a synchronous Python callback with three
arguments: the raw libcurl handle, the backend's SSL context pointer, and the
Python object supplied through ``CurlOpt.SSL_CTX_DATA`` (``None`` by default).
Return ``None`` or ``CurlECode.OK`` to continue, or another ``CurlECode`` to abort.
Exceptions raised by the callback abort the transfer and propagate to the caller,
including with ``AsyncCurl`` and ``AsyncSession``. Async callbacks are not supported.

The callback runs when libcurl creates a TLS context, after configuring its trust
store. The pointers are only valid during the callback; do not retain or free
them. On a low-level ``Curl`` handle the callback and its data persist across
transfers until replaced, reset or closed. Set ``SSL_CTX_FUNCTION`` to ``None``
to disable it. A duplicated handle retains its own callback registration with
the same Python data object.

The ``ssl_ctx_set_distrust`` helper rejects a chain containing a blocked public
key, even when a certificate using that key is present in the loaded CA store.
It accepts a non-empty list of 64-character hexadecimal SHA-256 hashes of
DER-encoded SubjectPublicKeyInfo (SPKI), **not certificate fingerprints**.
It checks the leaf, intermediates and root after normal chain validation, so
cross-signed and reissued certificates using the same key are also blocked.
It leaves the shared CA store unchanged. Calling it again on the same context
replaces that context's blocklist.

.. note::

   The helper requires a curl-impersonate build with the native
   ``curl_ssl_ctx_set_distrust`` API. Released curl-impersonate 2.3.0 does not
   include it. When built against older headers, the Python helper raises
   ``CurlError`` with ``CurlECode.NOT_BUILT_IN``; the general callback still works.

For example, read the public-key hashes you want to block from a file with one
hexadecimal hash per line:

.. code-block:: python

    from pathlib import Path
    from curl_cffi import CurlOpt, Session, ssl_ctx_set_distrust

    blocked_keys = Path("blocked-spki-sha256.txt").read_text().splitlines()

    def configure_tls(handle, ssl_ctx, blocked):
        ssl_ctx_set_distrust(ssl_ctx, blocked)

    with Session(curl_options={
        CurlOpt.SSL_CTX_FUNCTION: configure_tls,
        CurlOpt.SSL_CTX_DATA: blocked_keys,
        CurlOpt.FRESH_CONNECT: 1,
        CurlOpt.FORBID_REUSE: 1,
        CurlOpt.SSL_SESSIONID_CACHE: 0,
    }) as session:
        response = session.get("https://example.com")

The same options work with ``AsyncSession`` or ``Curl.setopt``. To obtain the
SPKI hash from a PEM certificate:

.. code-block:: shell

    openssl x509 -in affected-ca.pem -pubkey -noout \
        | openssl pkey -pubin -outform DER \
        | openssl dgst -sha256

Use only the 64 hexadecimal characters from the output. No blocklist is applied
automatically. Keep certificate and hostname verification enabled. The native
helper replaces any existing certificate verification callback and requires
successful backend chain validation, even if peer verification was disabled.
Native verification fallbacks such as Apple SecTrust are not used; the trust
anchor must be available in the backend's CA store.

Existing connections and resumed TLS sessions can bypass certificate verification.
Use a fresh connection pool when changing policy, or use the connection and
session-cache options shown above to require a full handshake for each transfer.
Do not enable TLS early data when policy must be checked before sending data.
Libcurl cannot track changes made inside your callback when deciding whether
connections or sessions can be reused.


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

   from curl_cffi import Session

   s = Session()
   s.get("https://example.com")
   s.upkeep()

``AsyncSession`` also exposes ``upkeep`` for idle connections in its pool:

.. code-block:: python

   from curl_cffi import AsyncSession

   async with AsyncSession() as s:
       await s.get("https://example.com")
       await s.upkeep()


Connection reuse across threads
===============================

A synchronous ``Session`` keeps one curl handle per thread (``use_thread_local_curl``,
on by default), because a curl handle is not safe to use from several threads at once.
The connection pool lives inside each handle, so connections — and options that act on
the pool such as ``MAXCONNECTS`` — are only reused *within* a thread. Reusing the same
``Session`` from a thread pool therefore opens at least one connection per thread.

libcurl does **not** support sharing the connection cache between concurrent threads,
so there is no safe way to pool the actual connections across the thread-local handles.
If you need real connection reuse across workers, use one ``Session`` per worker, or the
``AsyncSession``, whose connections are shared within its event loop.

What you *can* share across threads is the DNS cache and the TLS session cache, which
cuts the cost of reconnecting to the same host (DNS lookups and TLS handshakes). Pass a
``CurlShare`` to the session:

.. code-block:: python

   from curl_cffi import CurlShare, Session

   share = CurlShare()  # shares DNS + TLS sessions, safe across threads
   with Session(curl_share=share) as s:
       s.get("https://example.com")
   share.close()

The share is attached to every handle the session creates, including the ones used for
streaming and WebSocket responses. ``AsyncSession`` accepts the same ``curl_share=``
argument, sharing the DNS and TLS caches across the handles in its pool.

Keep the share alive until all attached handles have closed. ``share.close()``
raises ``CurlError`` if any handle is still using it; close those handles before
retrying cleanup.

``CurlShare`` can also share the connection cache (``CurlShare(connect=True)``), but that
is only safe when the handles are used serially, never from multiple concurrent threads.
