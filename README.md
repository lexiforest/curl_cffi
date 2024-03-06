# curl_cffi

[![Downloads](https://static.pepy.tech/badge/curl_cffi/week)](https://pepy.tech/project/curl_cffi)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/curl_cffi)
[![PyPI version](https://badge.fury.io/py/curl-cffi.svg)](https://badge.fury.io/py/curl-cffi)

[Documentation](https://curl-cffi.readthedocs.io) | [中文 README](https://github.com/yifeikong/curl_cffi/blob/main/README-zh.md) | [Discuss on Telegram](https://t.me/+lL9n33eZp480MGM1)

Python binding for [curl-impersonate](https://github.com/lwthiker/curl-impersonate)
via [cffi](https://cffi.readthedocs.io/en/latest/).

Unlike other pure python http clients like `httpx` or `requests`, `curl_cffi` can
impersonate browsers' TLS/JA3 and HTTP/2 fingerprints. If you are blocked by some
website for no obvious reason, you can give `curl_cffi` a try.

------

<a href="https://scrapfly.io/?utm_source=github&utm_medium=sponsoring&utm_campaign=curl_cffi" target="_blank"><img src="assets/scrapfly.png" alt="Scrapfly.io" width="149"></a>

[Scrapfly](https://scrapfly.io/?utm_source=github&utm_medium=sponsoring&utm_campaign=curl_cffi)
is an enterprise-grade solution providing Web Scraping API that aims to simplify the
scraping process by managing everything: real browser rendering, rotating proxies, and
fingerprints (TLS, HTTP, browser) to bypass all major anti-bots. Scrapfly also unlocks the
observability by providing an analytical dashboard and measuring the success rate/block
rate in detail.

Scrapfly is a good solution if you are looking for a cloud-managed solution for `curl_cffi`.
If you are managing TLS/HTTP fingerprint by yourself with `curl_cffi`, they also maintain
[this tool](https://scrapfly.io/web-scraping-tools/curl-python/curl_cffi) to convert curl
command into python curl_cffi code!

------

## Features

- Supports JA3/TLS and http2 fingerprints impersonation.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see [benchmarks](https://github.com/yifeikong/curl_cffi/tree/main/benchmark).
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports `asyncio` with proxy rotation on each request.
- Supports http 2.0, which requests does not.
- Supports websocket.

||requests|aiohttp|httpx|pycurl|curl_cffi|
|---|---|---|---|---|---|
|http2|❌|❌|✅|✅|✅|
|sync|✅|❌|✅|✅|✅|
|async|❌|✅|✅|❌|✅|
|websocket|❌|✅|❌|❌|✅|
|fingerprints|❌|❌|❌|❌|✅|
|speed|🐇|🐇🐇|🐇|🐇🐇|🐇🐇|

## Install

    pip install curl_cffi --upgrade

This should work on Linux, macOS and Windows out of the box.
If it does not work on you platform, you may need to compile and install `curl-impersonate`
first and set some environment variables like `LD_LIBRARY_PATH`.

To install beta releases:

    pip install curl_cffi --upgrade --pre

To install unstable version from GitHub:

    git clone https://github.com/yifeikong/curl_cffi/
    cd curl_cffi
    make preprocess
    pip install .

## Usage

`curl_cffi` comes with a low-level `curl` API and a high-level `requests`-like API.

Use the latest impersonate versions, do NOT copy `chrome110` here without changing.

### requests-like

```python
from curl_cffi import requests

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
```

### Sessions

```python
s = requests.Session()

# httpbin is a http test website, this endpoint makes the server set cookies
s.get("https://httpbin.org/cookies/set/foo/bar")
print(s.cookies)
# <Cookies[<Cookie foo=bar for httpbin.org />]>

# retrieve cookies again to verify
r = s.get("https://httpbin.org/cookies")
print(r.json())
# {'cookies': {'foo': 'bar'}}
```

Supported impersonate versions, as supported by my [fork](https://github.com/yifeikong/curl-impersonate) of [curl-impersonate](https://github.com/lwthiker/curl-impersonate):

However, only Chrome-like browsers are supported. Firefox support is tracked in [#59](https://github.com/yifeikong/curl_cffi/issues/59).

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116 <sup>[1]</sup>
- chrome119 <sup>[1]</sup>
- chrome120 <sup>[1]</sup>
- chrome99_android
- edge99
- edge101
- safari15_3 <sup>[2]</sup>
- safari15_5 <sup>[2]</sup>
- safari17_0 <sup>[1]</sup>
- safari17_2_ios <sup>[1]</sup>

Notes:
1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were [not correct](https://github.com/lwthiker/curl-impersonate/issues/215).

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

For low-level APIs, Scrapy integration and other advanced topics, see the
[docs](https://curl-cffi.readthedocs.io) for more details.

## Acknowledgement

- Originally forked from [multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), which is under the MIT license.
- Headers/Cookies files are copied from [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), which is under the BSD license.
- Asyncio support is inspired by Tornado's curl http client.
- The WebSocket API is inspired by [websocket_client](https://github.com/websocket-client/websocket-client).

## [Sponsor] Bypass Cloudflare with API

<a href="https://yescaptcha.com/i/stfnIO" target="_blank"><img src="assets/yescaptcha.png" alt="Yes Captcha!" height="47" width="149"></a>

Yescaptcha is a proxy service that bypasses Cloudflare and uses the API interface to obtain verified cookies (e.g. `cf_clearance`). Click [here](https://yescaptcha.com/i/stfnIO) to register: https://yescaptcha.com/i/stfnIO

## [Sponsor] ScrapeNinja

<a href="https://scrapeninja.net?utm_source=github&utm_medium=banner&utm_campaign=cffi" target="_blank"><img src="https://scrapeninja.net/img/logo_with_text_new5.svg" alt="Scrape Ninja" width="149"></a>

[ScrapeNinja](https://scrapeninja.net?utm_source=github&utm_medium=banner&utm_campaign=cffi) is a web scraping API with two engines: fast, with high performance and TLS
fingerprint; and slower with a real browser under the hood.

ScrapeNinja handles headless browsers, proxies, timeouts, retries, and helps with data
extraction, so you can just get the data in JSON. Rotating proxies are available out of
the box on all subscription plans.

## Sponsor

<a href="https://buymeacoffee.com/yifei" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
