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
   vs-requests
   faq
   api
   changelog

`Discuss on Telegram`_

.. _Discuss on Telegram: https://t.me/+lL9n33eZp480MGM1

curl_cffi is a Python binding for `curl-impersonate`_ via `cffi`_.

.. _curl-impersonate: https://github.com/lexiforest/curl-impersonate
.. _cffi: https://cffi.readthedocs.io/en/latest/

Unlike other pure Python http clients like ``httpx`` or ``requests``, ``curl_cffi`` can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

------

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/scrapfly.png
   :width: 300
   :alt: Scrapfly
   :target: https://scrapfly.io/?utm_source=github&utm_medium=sponsoring&utm_campaign=curl_cffi

`Scrapfly <https://scrapfly.io/?utm_source=github&utm_medium=sponsoring&utm_campaign=curl_cffi>`_
is an enterprise-grade solution providing Web Scraping API that aims to simplify the
scraping process by managing everything: real browser rendering, rotating proxies, and
fingerprints (TLS, HTTP, browser) to bypass all major anti-bots. Scrapfly also unlocks the
observability by providing an analytical dashboard and measuring the success rate/block
rate in details.

Scrapfly is a good solution if you are looking for a cloud-managed solution for ``curl_cffi``.
If you are managing TLS/HTTP fingerprint by yourself with ``curl_cffi``, they also maintain
a `curl to python converter <https://scrapfly.io/web-scraping-tools/curl-python/curl_cffi>`_ .

------

Features
------

- Supports JA3/TLS and http2 fingerprints impersonation.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see `benchmarks <https://github.com/lexiforest/curl_cffi/tree/main/benchmark>`_.
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports ``asyncio`` with proxy rotation on each request.
- Supports http 2.0, which requests does not.
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

    from curl_cffi import requests

    url = "https://tools.scrapfly.io/api/fp/ja3"

    # Notice the impersonate parameter
    r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome110")

    print(r.json())
    # output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
    # the js3n fingerprint should be the same as target browser

    # To keep using the latest browser version as `curl_cffi` updates,
    # simply set impersonate="chrome" without specifying a version.
    # Other similar values are: "safari" and "safari_ios"
    r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome")

    # http/socks proxies are supported
    proxies = {"https": "http://localhost:3128"}
    r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome110", proxies=proxies)

    proxies = {"https": "socks://localhost:3128"}
    r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome110", proxies=proxies)

Sessions
~~~~~~

.. code-block:: python

    s = requests.Session()

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

    from curl_cffi.requests import AsyncSession

    async with AsyncSession() as s:
        r = await s.get("https://example.com")

More concurrency:

.. code-block:: python

    import asyncio
    from curl_cffi.requests import AsyncSession

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

    from curl_cffi.requests import Session, WebSocket

    def on_message(ws: WebSocket, message):
        print(message)

    with Session() as s:
        ws = s.ws_connect(
            "wss://api.gemini.com/v1/marketdata/BTCUSD",
            on_message=on_message,
        )
        ws.run_forever()


Sponsor
------

Click `here <https://buymeacoffee.com/yifei>`_ to buy me a coffee.

Bypass Cloudflare with API
~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/yescaptcha.png
   :width: 149
   :alt: YesCaptcha
   :target: https://yescaptcha.com/i/stfnIO

`Yescaptcha <https://yescaptcha.com/i/stfnIO>`_ is a proxy service that bypasses Cloudflare and uses the API interface to
obtain verified cookies (e.g. ``cf_clearance``). Click `here <https://yescaptcha.com/i/stfnIO>`_
to register.

ScrapeNinja
~~~~~~

.. image:: https://scrapeninja.net/img/logo_with_text_new5.svg
   :width: 149
   :alt: ScrapeNinja
   :target: https://scrapeninja.net/?utm_source=github&utm_medium=banner&utm_campaign=cffi

`ScrapeNinja <https://scrapeninja.net/?utm_source=github&utm_medium=banner&utm_campaign=cffi>`_
is a web scraping API with two engines: fast, with high performance and TLS
fingerprint; and slower with a real browser under the hood. 

ScrapeNinja handles headless browsers, proxies, timeouts, retries, and helps with data
extraction, so you can just get the data in JSON. Rotating proxies are available out of
the box on all subscription plans.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
