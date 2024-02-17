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
   compile
   cookies
   vs-requests
   faq
   api
   changelog

[Documentation](https://curl-cffi.readthedocs.io) | [中文 README](https://github.com/yifeikong/curl_cffi/blob/main/README-zh.md) | [Discuss on Telegram](https://t.me/+lL9n33eZp480MGM1)

curl_cffi is a Python binding for [curl-impersonate](https://github.com/yifeikong/curl-impersonate)
via [cffi](https://cffi.readthedocs.io/en/latest/).

Unlike other pure Python http clients like ``httpx`` or ``requests``, ``curl_cffi`` can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

Features
------

- Supports JA3/TLS and http2 fingerprints impersonation.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see [benchmarks](https://github.com/yifeikong/curl_cffi/tree/main/benchmark).
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports ``asyncio`` with proxy rotation on each request.
- Supports http 2.0, which requests does not.
- Supports websocket.

|library|requests|aiohttp|httpx|pycurl|curl_cffi|
|---|---|---|---|---|---|
|http2|❌|❌|✅|✅|✅|
|sync|✅|❌|✅|✅|✅|
|async|❌|✅|✅|❌|✅|
|websocket|❌|✅|❌|❌|✅|
|fingerprints|❌|❌|❌|❌|✅|
|speed|🐇|🐇🐇|🐇|🐇🐇|🐇🐇|

Install
-----

    pip install curl_cffi --upgrade

For more details, see :doc:`install`.

Usage
------

requests-like
~~~~~~

```python
from curl_cffi import requests

# Notice the impersonate parameter
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome")

print(r.json())
# output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
# the js3n fingerprint should be the same as target browser

# http/socks proxies are supported
proxies = {"https": "http://localhost:3128"}
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)

proxies = {"https": "socks://localhost:3128"}
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)
```

Sessions
~~~~~~

```python
# sessions are supported
s = requests.Session()
# httpbin is a http test website
s.get("https://httpbin.org/cookies/set/foo/bar")
print(s.cookies)
# <Cookies[<Cookie foo=bar for httpbin.org />]>
r = s.get("https://httpbin.org/cookies")
print(r.json())
# {'cookies': {'foo': 'bar'}}
```

### asyncio

```python
from curl_cffi.requests import AsyncSession

async with AsyncSession() as s:
    r = await s.get("https://example.com")
```

More concurrency:

```python
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
```

### WebSockets

```python
from curl_cffi.requests import Session, WebSocket

def on_message(ws: WebSocket, message):
    print(message)

with Session() as s:
    ws = s.ws_connect(
        "wss://api.gemini.com/v1/marketdata/BTCUSD",
        on_message=on_message,
    )
    ws.run_forever()
```

### curl-like

Alternatively, you can use the low-level curl-like API:

```python
from curl_cffi import Curl, CurlOpt
from io import BytesIO

buffer = BytesIO()
c = Curl()
c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
c.setopt(CurlOpt.WRITEDATA, buffer)

c.impersonate("chrome110")

c.perform()
c.close()
body = buffer.getvalue()
print(body.decode())
```

See the [docs](https://curl-cffi.readthedocs.io) for more details.

### scrapy

If you are using scrapy, check out these middlewares:

- [tieyongjie/scrapy-fingerprint](https://github.com/tieyongjie/scrapy-fingerprint)
- [jxlil/scrapy-impersonate](https://github.com/jxlil/scrapy-impersonate)

## Acknowledgement

- Originally forked from [multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), which is under the MIT license.
- Headers/Cookies files are copied from [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), which is under the BSD license.
- Asyncio support is inspired by Tornado's curl http client.
- The WebSocket API is inspired by [websocket_client](https://github.com/websocket-client/websocket-client).

## [Sponsor] Bypass Cloudflare with API

<a href="https://yescaptcha.com/i/stfnIO" target="_blank"><img src="assets/yescaptcha.png" alt="Yes Captcha!" height="47" width="149"></a>

Yescaptcha is a proxy service that bypasses Cloudflare and uses the API interface to obtain verified cookies (e.g. `cf_clearance`). Click [here](https://yescaptcha.com/i/stfnIO) to register: https://yescaptcha.com/i/stfnIO

## Sponsor

<a href="https://buymeacoffee.com/yifei" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
