Quick Start
***********

Install
=======

Note: We only support Python 3.10 and above. Python 3.9 has reached its end of life.

Via pip
-------

The simplest way is to install from PyPI:

.. code-block::

    pip install curl_cffi --upgrade

We have sdist(source distribution) and bdist(binary distribution) on PyPI. This should
work on Linux, macOS and Windows out of the box.

If it does not work on you platform, you may need to compile and install ``curl-impersonate``
first and set some environment variables like ``LD_LIBRARY_PATH``.

Beta versions
-------------

To install beta releases:

.. code-block::

    pip install curl_cffi --upgrade --pre

Note the ``--pre`` option here means pre-releases.


Latest
------

To install the latest unstable version from GitHub:

.. code-block::

    git clone https://github.com/lexiforest/curl_cffi/
    cd curl_cffi
    make preprocess
    pip install .

Or you can download the wheels from github actions artifacts.

requests-like
=============

``curl_cffi`` tries to follow the ``requests`` API when possible, if you are already of guru using requests,
read the warning part in this page, skip other parts and head over to the :doc:`vs-requests`.


Basic GET requests
------------------

Basic ``GET`` request and using the ``impersonate`` parameter.

.. code-block:: python

    import curl_cffi

    url = "https://tls.browserleaks.com/json"

    # Notice the impersonate parameter
    r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome110")

    print(r.json())
    # output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
    # the js3n fingerprint should be the same as target browser

    # To keep using the latest browser version as `curl_cffi` updates,
    # simply set impersonate="chrome" without specifying a version.
    # Other similar values are: "safari" and "safari_ios"
    r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome")

    # http/socks proxies are supported
    proxies = {"https": "http://localhost:3128"}
    r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)

    proxies = {"https": "socks://localhost:3128"}
    r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)


URL params
----------

Messing with the URLs:

.. code-block:: python

    import curl_cffi

    >>> params = {"foo": "bar"}
    >>> r = requests.get("http://httpbin.org/get", params=params)
    >>> r.url
    'http://httpbin.org/get?foo=bar'

    >>> params = {'key1': 'value1', 'key2': ['value2', 'value3']}
    >>> import curl_cffi
    >>> r = curl_cffi.get('https://httpbin.org/get', params=params)
    >>> r.url
    'https://httpbin.org/get?key1=value1&key2=value2&key2=value3'


Headers
-------

Additional headers can be override with ``headers=...``.

.. code-block:: python

    headers = {"User-Agent": "curl_cffi/0.11.2"}
    r = curl_cffi.get("http://example.com", headers=headers)

.. warning::

    In curl_cffi, if you set ``impersonate=...``, by default, the corresponding headers will
    be added, you can:

    1. Add your headers to override them.
    2. Use ``default_headers=False`` to completely turn off the default headers.

.. code-block:: python

    >>> r = curl_cffi.get("https://httpbin.org/headers", impersonate="chrome")
    >>> print(r.text)
    {
      "headers": {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.9",
        "Host": "httpbin.org",
        "Priority": "u=0, i",
        "Sec-Ch-Ua": "\"Chromium\";v=\"136\", \"Google Chrome\";v=\"136\", \"Not.A/Brand\";v=\"99\"",
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": "\"macOS\"",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "X-Amzn-Trace-Id": "Root=1-68452cc9-7287427f222e720c57971297"
      }
    }

    >>> r = curl_cffi.get("https://httpbin.org/headers", impersonate="chrome", default_headers=False)
    >>> print(r.text)
    {
      "headers": {
        "Accept": "*/*",
        "Accept-Encoding": "gzip, deflate, br",
        "Host": "httpbin.org",
        "X-Amzn-Trace-Id": "Root=1-68452d20-2cf4cf00201987301c476c06"
      }
    }


Reading Response
----------------

Like requests, you can read the response content in the following ways:

Reading the binary content as bytes:

.. code-block:: python

    >>> r = curl_cffi.get("https://example.com")
    >>> r.content
    b'<!doctype html>\n<html>\n<head>\n...'


Reading the decoded content as str:

.. code-block:: python

    >>> r = curl_cffi.get("https://example.com")
    >>> r.text
    '<!doctype html>\n<html>\n<head>\n...'

By default, ``curl_cffi`` first use the ``encoding`` attribute if given, then tries to use the
``Content-Type`` header to decode the content, If not found, will fallback to ``default_encoding``,
then to "utf-8".

.. code-block:: python

    # force override with .encoding
    >>> r.encoding = 'latin-1'

POST and uploads
----------------

Of course, we also support ``POST``, ``PUT``, ``DELETE`` etc.

Form submit
~~~~~~~~~~~

Use the ``data={...}`` option.

.. note::

   The "application/x-www-form-urlencoded" will be automatically added.

.. code-block:: python

    >>> r = curl_cffi.post("https://httpbin.org/post", data={"name": "Luke"})
    >>> print(r.text)
    {
      "args": {},
      "form": {
        "name": "Luke"
      },
      ...
    }

Binary data
~~~~~~~~~~~

Still, use the ``data=b"..."`` option.

.. code-block:: python

    >>> r = curl_cffi.post("https://httpbin.org/post", data=b"LukeSkywalker")
    >>> print(r.text)
    {
      "args": {},
      "data": "LukeSkywalker",
      "files": {},
      "form": {},
      ...
    }

Posting JSON
~~~~~~~~~~~~

Use the ``json=...`` option.

.. note::

   The "application/json" will be automatically added.

.. code-block:: python

    >>> r = curl_cffi.post("https://httpbin.org/post", json={"name": "Luke"})
    >>> print(r.text)
    {
      "args": {},
      "data": "{\"name\":\"Luke\"}",
      "files": {},
      "form": {},
      ...
    }

Uploads
~~~~~~~

.. warning::

    curl_cffi does not support the ``files=...`` API. Use ``multipart=...`` instead.

For uploading files, the ``requests`` API is horrible, we provide a similar but cleaner way:

.. code-block:: python

    mp = curl_cffi.CurlMime()

    mp.addpart(
        name="attachment",         # field name in the form
        content_type="image/png",  # mime type
        filename="image.png",      # filename seen by remote server
        local_path="./image.png",  # local file to upload
        data=file.read(),          # if you already have the data in memory
    )

    r = curl_cffi.post("https://httpbin.org/post", data={"foo": "bar"}, multipart=mp)
    print(r.json())

All the fields in the API are explicit. For advanced usage: see `examples <https://github.com/lexiforest/curl_cffi/blob/main/examples/upload.py>`_.


Compressed response
-------------------

Currently, we forcefully decode compressed response, but this may be changed in the future.

curl_cffi supports gzip/brotli/zstd natively.

If the response content is ``json``, you can parse them directly:

.. code-block:: python

    >>> r = curl_cffi.get("https://httpbin.org/headers")
    >>> r.json()
    {'headers': {'Accept': '*/*', 'Accept-Encoding': 'gz...')


Response status
---------------

.. code-block:: python

    >>> r = curl_cffi.get('https://httpbin.org/get')
    >>> r.status_code
    200

    >>> r = curl_cffi.get("https://httpbin.org/status/404")
    >>> r.status_code
    404
    >>> r.raise_for_status()
    Traceback (most recent call last):
      File "<stdin>", line 1, in <module>
      File "/Users/.../repos/curl_cffi/curl_cffi/requests/models.py", line 167, in raise_for_status
        raise HTTPError(f"HTTP Error {self.status_code}: {self.reason}", 0, self)
    curl_cffi.requests.exceptions.HTTPError: HTTP Error 404:

Response headers
----------------

Response headers is a case-insensitive dict.

.. code-block:: python


    >>> r.headers
    Headers({'date': 'Sun, 08 Jun 2025 06:58:15 GMT', 'content-type': 'application/json', 'content-length': '184', 'server': 'gunicorn/19.9.0', 'access-control-allow-origin': '*', 'access-control-allow-credentials': 'true'})
    >>> r.headers["content-type"]
    'application/json'

For a complete list of response attributes, see the :doc:`api`.

Streaming response
------------------

For compatibility, curl_cffi supports the ``stream=True`` option, and a ``stream`` method,
with iterative-style content streaming.

But when possible, you should choose the native ``content_callback`` option.

.. code-block:: python

    r = curl_cffi.get(

    >>> r = curl_cffi.get("https://httpbin.org/stream/20", stream=True)
    >>> for chunk in r.iter_content():
    ...     print("CHUNK", chunk)
    ...
    CHUNK b'{"url": "https://httpbin.org/stream/20",...'
    CHUNK b'{"url": "https://httpbin.org/stream/20",...'


For more examples, see the `examples on GitHub <https://github.com/lexiforest/curl_cffi/blob/main/examples/stream.py>`_

.. warning::

    Natively, libcurl only support a callback-style API, i.e. you pass a callback function for
    processing the streamed response content. In curl_cffi, we use a internal queue to convert
    the callback to a interative API.

    Because of the limitation, when a request is sent, the response will start to be streamed to
    your client at once. You need to start consuming the content immediately, otherwise, it would
    be store in your memory, thus OOM could be triggered.

    Alternatively, you should use the native ``content_callback`` API.

.. code-block:: python

    >>> def callback(chunk):
    ...     print("CHUNK", chunk)
    ...
    >>> r = curl_cffi.get("https://httpbin.org/stream/20", content_callback=callback)
    CHUNK b'{"url": "https://httpbin.org/stream/20"...'
    CHUNK b'{"url": "https://httpbin.org/stream/20"...'


Redirection and history
-----------------------

``curl_cffi`` automatically follows redirects, use ``allow_redirects=False`` to disable it.

.. code-block:: python

    >>> r = curl_cffi.get("https://httpbin.org/redirect-to?url=/")
    >>> r.url
    'https://httpbin.org/'


    >>> r = requests.get("https://httpbin.org/redirect-to?url=/", allow_redirects=False)
    >>> r.url
    'https://httpbin.org/redirect-to?url=/'
    >>> r.status_code
    302

.. warning::

    History is not implemented.


Authenticate
------------

You can use the ``auth`` parameter or URL to add http ``basic auth`` credentials.

.. code-block:: python

    >>> curl_cffi.get("https://example.com", auth=("my_user", "password123"))

    >>> curl_cffi.get("https://user:password@example.com")


Digest auth is dangerous and `deprecated <https://en.wikipedia.org/wiki/Digest_access_authentication#Disadvantages>`_,
we do not support that. Although, you should be able to use it with low-level curl options.


Sessions and cookies
--------------------

We also provide Session to persist cookies and reuse connections.

.. note::

   You should always use a session whenever possible.

.. code-block:: python

    s = curl_cffi.Session()

    # Cookies from server are stored in session
    s.get("https://httpbin.org/cookies/set/foo/bar")

    print(s.cookies)
    # <Cookies[<Cookie foo=bar for httpbin.org />]>

    # Cookies are used in next request
    r = s.get("https://httpbin.org/cookies")
    print(r.json())
    # {'cookies': {'foo': 'bar'}}

    # It's preferred to use a context manager
    with curl_cffi.Session() as s:
        r = s.get("https://example.com")

If you want to set a global option in ``Session``, you can use the same parameter in ``request``.

.. code-block:: python

    with curl_cffi.Session(headers={"User-Agent": "curl_cffi/0.11"}) as s:
        r = s.get("https://example.com")

For a complete list, see :doc:`api`

Retries
~~~~~~~

Use ``retry`` to automatically re-run failed requests.

.. code-block:: python

    from curl_cffi import Session, RetryStrategy

    # Simple count-based retries
    with Session(retry=2) as s:
        r = s.get("https://example.com")

    # Custom strategy with delay/backoff/jitter
    strategy = RetryStrategy(count=3, delay=0.2, jitter=0.1, backoff="exponential")
    with Session(retry=strategy) as s:
        r = s.get("https://example.com")

Response vs Session cookies
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``response.cookies`` object contains only cookies from current request. Be aware, if you hit a redirect,
response cookies may be incomplete, it's almost always better to use a session.

.. code-block:: python

    import curl_cffi
    r = curl_cffi.get("https://httpbin.org/redirect")

    # ❌ Cookie from previous redirect may be lost.
    do_something(r.cookies)


    s = curl_cffi.Session()
    r = s.get("https://httpbin.org/redirect")

    # ✅ Use a session instead, to retrive all cookies in the session
    do_something(s.cookies)

Use session without cookies
~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you want to use a session, but somehow you need to discard all the cookies. You can use the
``discard_cookies`` option to discard cookies in session.

.. code-block:: python

    s = curl_cffi.Session(discard_cookies=True)


Asyncio
=======

Besides the regular sync API, ``curl_cffi`` also provides a very similar ``asyncio`` API.

.. code-block:: python

    # You must use a session for asyncio
    async with curl_cffi.AsyncSession() as s:
        r = await s.get("https://example.com")

The benefit of asyncio is easier way to implement more concurrency:

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    urls = [
        "https://google.com/",
        "https://facebook.com/",
        "https://apple.com/",
    ]

    async with AsyncSession() as s:
        tasks = []
        for url in urls:
            task = s.get(url)
            tasks.append(task)
        results = await asyncio.gather(*tasks)

For detailed asyncio guide, see :doc:`asyncio`.

WebSockets
==========

``curl_cffi`` supports both sync and async API for websockets.

.. code-block:: python

    from curl_cffi import Session, WebSocket

    def on_message(ws: WebSocket, message):
        print(message)

    with Session() as session:
        ws = session.ws_connect(
            "wss://api.gemini.com/v1/marketdata/BTCUSD",
            on_message=on_message,
        )
        ws.run_forever()

    # asyncio
    import asyncio
    from curl_cffi import AsyncSession

    async with AsyncSession() as session:
        async with session.ws_connect("wss://echo.websocket.org") as ws:
            await asyncio.gather(*[ws.send_str("Hello, World!") for _ in range(10)])
            async for message in ws:
                print(message)

For detailed websocket guide, see :doc:`websockets`.
