.. curl_cffi documentation master file, created by
   sphinx-quickstart on Sat Feb 17 22:22:59 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to curl_cffi's documentation!
=====================================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   install
   impersonate
   cookies
   advanced
   exceptions
   vs-requests
   faq
   api
   changelog

`Discuss on Telegram`_

.. _Discuss on Telegram: https://t.me/+lL9n33eZp480MGM1

curl_cffi is a Python binding for `curl-impersonate fork`_ via `cffi`_. For commercial
support, visit `impersonate.pro <https://impersonate.pro>`_.

.. _curl-impersonate: https://github.com/lexiforest/curl-impersonate
.. _cffi: https://cffi.readthedocs.io/en/latest/

Unlike other pure Python http clients like ``httpx`` or ``requests``, ``curl_cffi`` can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

Sponsors
------

SerpAPI
~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/serpapi.png
   :width: 100
   :alt: SerpAPI
   :target: https://serpapi.com

Scrape Google and other search engines from `SerpApi <https://serpapi.com/>`_'s fast, easy,
and complete API. 0.66s average response time (≤ 0.5s for Ludicrous Speed Max accounts),
99.95% SLAs, pay for successful responses only.

Bypass Cloudflare with API
~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/yescaptcha.png
   :width: 149
   :alt: YesCaptcha
   :target: https://yescaptcha.com/i/stfnIO

`Yescaptcha <https://yescaptcha.com/i/stfnIO>`_ is a proxy service that bypasses Cloudflare and uses the API interface to
obtain verified cookies (e.g. ``cf_clearance``). Click `here <https://yescaptcha.com/i/stfnIO>`_
to register.

Easy Captcha Bypass for Scraping
~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/capsolver.jpg
   :width: 170
   :alt: Capsolver
   :target: https://www.capsolver.com/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi

`CapSolver <https://www.capsolver.com/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi>`_
is an AI-powered tool that easily bypasses Captchas, allowing uninterrupted access to
public data. It supports a variety of Captchas and works seamlessly with ``curl_cffi``,
Puppeteer, Playwright, and more. Fast, reliable, and cost-effective. Plus, ``curl_cffi``
users can use the code **"CURL"** to get an extra 6% balance! and register `here <https://dashboard.capsolver.com/passport/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi>`_


You can also click `here <https://buymeacoffee.com/yifei>`_ to buy me a coffee.

------

Features
------

- Supports JA3/TLS and http2 fingerprints impersonation, including recent browsers and custom fingerprints.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see `benchmarks <https://github.com/lexiforest/curl_cffi/tree/main/benchmark>`_.
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports ``asyncio`` with proxy rotation on each request.
- Supports http 2.0 & 3.0, which requests does not.
- Supports websocket.

.. list-table:: Feature matrix
   :widths: 20 16 16 16 16 16
   :header-rows: 1

   * - 
     - requests
     - aiohttp
     - httpx
     - pycurl
     - curl_cffi
   * - http2
     - ❌
     - ❌
     - ✅
     - ✅
     - ✅
   * - http3
     - ❌
     - ❌
     - ❌
     - ☑️
     - ☑️
   * - sync
     - ✅
     - ❌
     - ✅
     - ✅
     - ✅
   * - async
     - ❌
     - ✅
     - ✅
     - ❌
     - ✅
   * - websocket
     - ❌
     - ✅
     - ❌
     - ❌
     - ✅
   * - fingerprints
     - ❌
     - ❌
     - ❌
     - ❌
     - ✅
   * - speed
     - 🐇
     - 🐇🐇
     - 🐇
     - 🐇🐇
     - 🐇🐇

Notes:

1. For pycurl, you need a http/3 enabled libcurl to make it work, while curl_cffi packages libcurl-impersonate inside Python wheels.
2. Since v0.11.0. However, only Linux and macOS are supported, Windows is not supported due to failed building of ngtcp2.

Install
-----

.. code-block:: sh

    pip install curl_cffi --upgrade

For more details, see :doc:`install`.

Basic Usage
------

requests-like
~~~~~~

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

Sessions
~~~~~~

.. code-block:: python

    s = curl_cffi.Session()

    # httpbin is a http test website
    s.get("https://httpbin.org/cookies/set/foo/bar")

    print(s.cookies)
    # <Cookies[<Cookie foo=bar for httpbin.org />]>

    r = s.get("https://httpbin.org/cookies")
    print(r.json())
    # {'cookies': {'foo': 'bar'}}

asyncio
~~~~~~

.. code-block:: python

    async with curl_cffi.AsyncSession() as s:
        r = await s.get("https://example.com")

More concurrency:

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    urls = [
        "https://google.com/",
        "https://facebook.com/",
        "https://twitter.com/",
    ]

    async with AsyncSession() as s:
        tasks = []
        for url in urls:
            task = s.get(url)
            tasks.append(task)
        results = await asyncio.gather(*tasks)

WebSockets
~~~~~~

.. code-block:: python

    from curl_cffi import Session, WebSocket

    def on_message(ws: WebSocket, message):
        print(message)

    with Session() as s:
        ws = s.ws_connect(
            "wss://api.gemini.com/v1/marketdata/BTCUSD",
            on_message=on_message,
        )
        ws.run_forever()

    # asyncio
    import asyncio
    from curl_cffi import AsyncSession

    async with AsyncSession() as s:
        ws = await s.ws_connect("wss://echo.websocket.org")
        await asyncio.gather(*[ws.send_str("Hello, World!") for _ in range(10)])
        async for message in ws:
            print(message)


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
