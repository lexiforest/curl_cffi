# curl_cffi

![PyPI - Downloads](https://img.shields.io/pypi/dm/curl-cffi)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/curl_cffi)
[![PyPI version](https://badge.fury.io/py/curl-cffi.svg)](https://badge.fury.io/py/curl-cffi)
[![Generic badge](https://img.shields.io/badge/Telegram%20Group-join-blue?logo=telegram)](https://t.me/+lL9n33eZp480MGM1)
[![Generic badge](https://img.shields.io/badge/Discord-join-purple?logo=blue)](https://discord.gg/kJqMHHgdn2)

[Documentation](https://curl-cffi.readthedocs.io)

Python binding for [curl-impersonate fork](https://github.com/lexiforest/curl-impersonate)
via [cffi](https://cffi.readthedocs.io/en/latest/). For commercial support, visit [impersonate.pro](https://impersonate.pro).

Unlike other pure python http clients like `httpx` or `requests`, `curl_cffi` can
impersonate browsers' TLS/JA3 and HTTP/2 fingerprints. If you are blocked by some
website for no obvious reason, you can give `curl_cffi` a try.

Python 3.9 is the minimum supported version since v0.10.

## Sponsors

Maintenance of this project is made possible by all the <a href="https://github.com/lexiforest/curl_cffi/graphs/contributors">contributors</a> and <a href="https://github.com/sponsors/lexiforest">sponsors</a>. If you'd like to sponsor this project and have your avatar or company logo appear below <a href="https://github.com/sponsors/lexiforest">click here</a>. 💖

------

<a href="https://serpapi.com/" target="_blank"><img src="https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/serpapi.png" alt="SerpAPI" height="67" width="63"></a>

Scrape Google and other search engines from [SerpApi](https://serpapi.com/)'s fast, easy, and complete API. 0.66s average response time (≤ 0.5s for Ludicrous Speed Max accounts), 99.95% SLAs, pay for successful responses only.

------

### Bypass Cloudflare with API

<a href="https://yescaptcha.com/i/stfnIO" target="_blank"><img src="https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/yescaptcha.png" alt="Yes Captcha!" height="47" width="149"></a>

Yescaptcha is a proxy service that bypasses Cloudflare and uses the API interface to
obtain verified cookies (e.g. `cf_clearance`). Click [here](https://yescaptcha.com/i/stfnIO)
to register: https://yescaptcha.com/i/stfnIO

------

### Easy Captcha Bypass for Scraping

<a href="https://www.capsolver.com/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi" target="_blank"><img src="https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/capsolver.jpg" alt="CapSolver" height="50" width="178"></a>

[CapSolver](https://www.capsolver.com/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi)
is an AI-powered tool that easily bypasses Captchas, allowing uninterrupted access to
public data. It supports a variety of Captchas and works seamlessly with `curl_cffi`,
Puppeteer, Playwright, and more. Fast, reliable, and cost-effective. Plus, `curl_cffi`
users can use the code **"CURL"** to get an extra 6% balance! and register [here](https://dashboard.capsolver.com/passport/?utm_source=github&utm_medium=banner_repo&utm_campaign=scraping&utm_term=curl_cffi).

------

## Features

- Supports JA3/TLS and http2 fingerprints impersonation, including recent browsers and custom fingerprints.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see [benchmarks](https://github.com/lexiforest/curl_cffi/tree/main/benchmark).
- Mimics the requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports `asyncio` with proxy rotation on each request.
- Supports http 2.0 & 3.0, which requests does not.
- Supports websocket.

||requests|aiohttp|httpx|pycurl|curl_cffi|
|---|---|---|---|---|---|
|http/2|❌|❌|✅|✅|✅|
|http/3|❌|❌|❌|☑️<sup>1</sup>|☑️<sup>2</sup>|
|sync|✅|❌|✅|✅|✅|
|async|❌|✅|✅|❌|✅|
|websocket|❌|✅|❌|❌|✅|
|fingerprints|❌|❌|❌|❌|✅|
|speed|🐇|🐇🐇|🐇|🐇🐇|🐇🐇|

Notes:
1. For pycurl, you need a http/3 enabled libcurl to make it work, while curl_cffi packages libcurl-impersonate inside Python wheels.
2. Since v0.11.0. However, only Linux and macOS are supported, Windows is not supported due to failed building of ngtcp2.

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

On macOS, you may need to install the following dependencies:

    brew install zstd nghttp2

## Usage

`curl_cffi` comes with a low-level `curl` API and a high-level `requests`-like API.

### requests-like

v0.9:

```py
from curl_cffi import requests

r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome")
```

v0.10:

```python
import curl_cffi

# Notice the impersonate parameter
r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome")

print(r.json())
# output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
# the js3n fingerprint should be the same as target browser

# To keep using the latest browser version as `curl_cffi` updates,
# simply set impersonate="chrome" without specifying a version.
# Other similar values are: "safari" and "safari_ios"
r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome")

# Randomly choose a browser version based on current market share in real world
# from: https://caniuse.com/usage-table
# NOTE: this is a pro feature.
r = curl_cffi.get("https://example.com", impersonate="realworld")

# To pin a specific version, use version numbers together.
r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome124")

# To impersonate other than browsers, bring your own ja3/akamai strings
# See examples directory for details.
r = curl_cffi.get("https://tls.browserleaks.com/json", ja3=..., akamai=...)

# http/socks proxies are supported
proxies = {"https": "http://localhost:3128"}
r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome", proxies=proxies)

proxies = {"https": "socks://localhost:3128"}
r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome", proxies=proxies)
```

### Sessions

v0.9:

```py
from curl_cffi import requests

s = requests.Session()
```

v0.10:

```python
s = curl_cffi.Session()

# httpbin is a http test website, this endpoint makes the server set cookies
s.get("https://httpbin.org/cookies/set/foo/bar")
print(s.cookies)
# <Cookies[<Cookie foo=bar for httpbin.org />]>

# retrieve cookies again to verify
r = s.get("https://httpbin.org/cookies")
print(r.json())
# {'cookies': {'foo': 'bar'}}
```

### Supported impersonate browsers

`curl_cffi` supports the same browser versions as supported by my [fork](https://github.com/lexiforest/curl-impersonate) of [curl-impersonate](https://github.com/lwthiker/curl-impersonate):

Open source version of curl_cffi includes versions whose fingerprints differ from previous versions.
If you see a version, e.g. `chrome135`, were skipped, you can simply impersonate it with your own headers and the previous version.

If you don't want to look up the headers etc, by yourself, consider buying commercial support from [impersonate.pro](https://impersonate.pro),
we have comprehensive browser fingerprints database for almost all the browser versions on various platforms.

If you are trying to impersonate a target other than a browser, use `ja3=...` and `akamai=...`
to specify your own customized fingerprints. See the [docs on impersonation](https://curl-cffi.readthedocs.io/en/latest/impersonate.html) for details.

|Browser|Open Source| Pro version|
|---|---|---|
|Chrome|chrome99, chrome100, chrome101, chrome104, chrome107, chrome110, chrome116<sup>[1]</sup>, chrome119<sup>[1]</sup>, chrome120<sup>[1]</sup>, chrome123<sup>[3]</sup>, chrome124<sup>[3]</sup>, chrome131<sup>[4]</sup>, chrome133a<sup>[5][6]</sup>, chrome136<sup>[6]</sup>|chrome132, chrome134, chrome135|
|Chrome Android| chrome99_android, chrome131_android <sup>[4]</sup>|chrome132_android, chrome133_android, chrome134_android, chrome135_android|
|Chrome iOS|N/A|coming soon|
|Safari <sup>[7]</sup>|safari15_3 <sup>[2]</sup>, safari15_5 <sup>[2]</sup>, safari17_0 <sup>[1]</sup>, safari18_0 <sup>[4]</sup>, safari18_4 <sup>[6]</sup>|coming soon|
|Safari iOS <sup>[7]</sup>| safari17_2_ios<sup>[1]</sup>, safari18_0_ios<sup>[4]</sup>, safari18_4_ios <sup>[6]</sup>|coming soon|
|Firefox|firefox133<sup>[5]</sup>, firefox135<sup>[7]</sup>|coming soon|
|Firefox Android|N/A|firefox135_android|
|Tor|tor145 <sup>[7]</sup>|coming soon|
|Edge|edge99, edge101|edge133, edge135|
|Opera|N/A|coming soon|
|Brave|N/A|coming soon|


Notes:
1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were [not correct](https://github.com/lwthiker/curl-impersonate/issues/215).
3. Added in version `0.7.0`.
4. Added in version `0.8.0`.
5. Added in version `0.9.0`.
6. The version postfix `-a`(e.g. `chrome133a`) means that this is an alternative version, i.e. the fingerprint has not been officially updated by browser, but has been observed because of A/B testing.
5. Added in version `0.10.0`.
6. Added in version `0.11.0`.
7. Since `0.11.0`, the format `safari184_ios` is preferred over `safari18_4_ios`, both are supported, but the latter is quite confusing and hard to parse.

### Asyncio

```python
from curl_cffi import AsyncSession

async with AsyncSession() as s:
    r = await s.get("https://example.com")
```

More concurrency:

```python
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
```

For low-level APIs, Scrapy integration and other advanced topics, see the
[docs](https://curl-cffi.readthedocs.io) for more details.


### WebSockets

```python
from curl_cffi import WebSocket

def on_message(ws: WebSocket, message: str | bytes):
    print(message)

ws = WebSocket(on_message=on_message)
ws.run_forever("wss://api.gemini.com/v1/marketdata/BTCUSD")
```

### Asyncio WebSockets

```python
import asyncio
from curl_cffi import AsyncSession

async with AsyncSession() as s:
    ws = await s.ws_connect("wss://echo.websocket.org")
    await asyncio.gather(*[ws.send_str("Hello, World!") for _ in range(10)])
    async for message in ws:
        print(message)
```

## Ecosystem

- Integrating with Scrapy: [jxlil/scrapy-impersonate](https://github.com/jxlil/scrapy-impersonate) and [tieyongjie/scrapy-fingerprint](https://github.com/tieyongjie/scrapy-fingerprint).
- Integrating with [requests](https://github.com/el1s7/curl-adapter), [httpx](https://github.com/vgavro/httpx-curl-cffi) as adapter.
- Integrating with captcha resolvers: [CapSolver](https://docs.capsolver.com/en/api/), [YesCaptcha](https://yescaptcha.atlassian.net/wiki/spaces/YESCAPTCHA/overview). Please see the head area for promo code and link.

## Acknowledgement

- Originally forked from [multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), which is under the MIT license.
- Headers/Cookies files are copied from [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), which is under the BSD license.
- Asyncio support is inspired by Tornado's curl http client.
- The synchronous WebSocket API is inspired by [websocket_client](https://github.com/websocket-client/websocket-client).
- The asynchronous WebSocket API is inspired by [aiohttp](https://github.com/aio-libs/aiohttp).

