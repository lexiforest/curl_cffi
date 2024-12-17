# curl_cffi

![PyPI - Downloads](https://img.shields.io/pypi/dm/curl-cffi)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/curl_cffi)
[![PyPI version](https://badge.fury.io/py/curl-cffi.svg)](https://badge.fury.io/py/curl-cffi)
[![Generic badge](https://img.shields.io/badge/Telegram%20Group-join-blue?logo=telegram)](https://t.me/+lL9n33eZp480MGM1)
[![Generic badge](https://img.shields.io/badge/Discord-join-purple?logo=blue)](https://discord.gg/kJqMHHgdn2)

[Documentation](https://curl-cffi.readthedocs.io)

Python binding for [curl-impersonate fork](https://github.com/lexiforest/curl-impersonate)
via [cffi](https://cffi.readthedocs.io/en/latest/).

Unlike other pure python http clients like `httpx` or `requests`, `curl_cffi` can
impersonate browsers' TLS/JA3 and HTTP/2 fingerprints. If you are blocked by some
website for no obvious reason, you can give `curl_cffi` a try.

Only Python 3.8 and above are supported. Python 3.7 has reached its end of life.

------

<a href="https://nubela.co/proxycurl/?utm_campaign=influencer_marketing&utm_source=github&utm_medium=social&utm_term=-&utm_content=lexiforest-curl_cffi" target="_blank"><img src="https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/proxycurl.png" alt="ProxyCurl" height="63" width="120"></a>

Scrape public LinkedIn profile data at scale with [Proxycurl APIs](https://nubela.co/proxycurl/?utm_campaign=influencer_marketing&utm_source=github&utm_medium=social&utm_term=-&utm_content=lexiforest-curl_cffi). Built for developers, by developers.

- GDPR, CCPA, SOC2 compliant
- High rate limit (300 requests/min), Fast (APIs respond in ~2s), High accuracy
- Fresh data - 88% of data is scraped real-time, other 12% is <29 days
- Tons of data points returned per profile

------

### Bypass Cloudflare with API

<a href="https://yescaptcha.com/i/stfnIO" target="_blank"><img src="https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/yescaptcha.png" alt="Yes Captcha!" height="47" width="149"></a>

Yescaptcha is a proxy service that bypasses Cloudflare and uses the API interface to
obtain verified cookies (e.g. `cf_clearance`). Click [here](https://yescaptcha.com/i/stfnIO)
to register: https://yescaptcha.com/i/stfnIO

------

<a href="https://scrapeninja.net?utm_source=github&utm_medium=banner&utm_campaign=cffi" target="_blank"><img src="https://scrapeninja.net/img/logo_with_text_new5.svg" alt="Scrape Ninja" width="149"></a>

[ScrapeNinja](https://scrapeninja.net?utm_source=github&utm_medium=banner&utm_campaign=cffi) is a web scraping API with two engines: fast, with high performance and TLS
fingerprint; and slower with a real browser under the hood.

ScrapeNinja handles headless browsers, proxies, timeouts, retries, and helps with data
extraction, so you can just get the data in JSON. Rotating proxies are available out of
the box on all subscription plans.

------

## Features

- Supports JA3/TLS and http2 fingerprints impersonation, including recent browsers and custome fingerprints.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see [benchmarks](https://github.com/lexiforest/curl_cffi/tree/main/benchmark).
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

    git clone https://github.com/lexiforest/curl_cffi/
    cd curl_cffi
    make preprocess
    pip install .

## Usage

`curl_cffi` comes with a low-level `curl` API and a high-level `requests`-like API.

### requests-like

```python
from curl_cffi import requests

# Notice the impersonate parameter
r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome")

print(r.json())
# output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
# the js3n fingerprint should be the same as target browser

# To keep using the latest browser version as `curl_cffi` updates,
# simply set impersonate="chrome" without specifying a version.
# Other similar values are: "safari" and "safari_ios"
r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome")

# To pin a specific version, use version numbers together.
r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome124")

# To impersonate other than browsers, bring your own ja3/akamai strings
# See examples directory for details.
r = requests.get("https://tls.browserleaks.com/json", ja3=..., akamai=...)

# http/socks proxies are supported
proxies = {"https": "http://localhost:3128"}
r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome", proxies=proxies)

proxies = {"https": "socks://localhost:3128"}
r = requests.get("https://tools.scrapfly.io/api/fp/ja3", impersonate="chrome", proxies=proxies)
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

`curl_cffi` supports the same browser versions as supported by my [fork](https://github.com/lexiforest/curl-impersonate) of [curl-impersonate](https://github.com/lwthiker/curl-impersonate):

However, only WebKit-based browsers are supported. Firefox support is tracked in [#59](https://github.com/lexiforest/curl_cffi/issues/59).

Browser versions will be added **only** when their fingerprints change. If you see a version, e.g.
chrome122, were skipped, you can simply impersonate it with your own headers and the previous version.

If you are trying to impersonate a target other than a browser, use `ja3=...` and `akamai=...`
to specify your own customized fingerprints. See the [docs on impersonatation](https://curl-cffi.readthedocs.io/en/latest/impersonate.html) for details.

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116 <sup>[1]</sup>
- chrome119 <sup>[1]</sup>
- chrome120 <sup>[1]</sup>
- chrome123 <sup>[3]</sup>
- chrome124 <sup>[3]</sup>
- chrome131 <sup>[4]</sup>
- chrome99_android
- chrome131_android <sup>[4]</sup>
- edge99
- edge101
- safari15_3 <sup>[2]</sup>
- safari15_5 <sup>[2]</sup>
- safari17_0 <sup>[1]</sup>
- safari17_2_ios <sup>[1]</sup>
- safari18_0 <sup>[4]</sup>
- safari18_0_ios <sup>[4]</sup>

Notes:
1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were [not correct](https://github.com/lwthiker/curl-impersonate/issues/215).
3. Added in version `0.7.0`.
4. Added in version `0.8.0`.

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
from curl_cffi.requests import WebSocket

def on_message(ws: WebSocket, message: str | bytes):
    print(message)

ws = WebSocket(on_message=on_message)
ws.run_forever("wss://api.gemini.com/v1/marketdata/BTCUSD")
```

For low-level APIs, Scrapy integration and other advanced topics, see the
[docs](https://curl-cffi.readthedocs.io) for more details.

### asyncio WebSockets

```python
import asyncio
from curl_cffi.requests import AsyncSession

async with AsyncSession() as s:
    ws = await s.ws_connect("wss://echo.websocket.org")
    await asyncio.gather(*[ws.send_str("Hello, World!") for _ in range(10)])
    async for message in ws:
        print(message)
```

## Acknowledgement

- Originally forked from [multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), which is under the MIT license.
- Headers/Cookies files are copied from [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), which is under the BSD license.
- Asyncio support is inspired by Tornado's curl http client.
- The synchronous WebSocket API is inspired by [websocket_client](https://github.com/websocket-client/websocket-client).
- The asynchronous WebSocket API is inspired by [aiohttp](https://github.com/aio-libs/aiohttp).


## Sponsor

<a href="https://buymeacoffee.com/yifei" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
