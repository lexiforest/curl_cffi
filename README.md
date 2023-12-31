# curl_cffi

Python binding for [curl-impersonate](https://github.com/lwthiker/curl-impersonate)
via [cffi](https://cffi.readthedocs.io/en/latest/).

[Documentation](https://curl-cffi.readthedocs.io) | [中文 README](https://github.com/yifeikong/curl_cffi/blob/master/README-zh.md) | [Discuss on Telegram](https://t.me/+lL9n33eZp480MGM1)

Unlike other pure python http clients like `httpx` or `requests`, `curl_cffi` can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

## Features

- Supports JA3/TLS and http2 fingerprints impersonation.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see [benchmarks](https://github.com/yifeikong/curl_cffi/tree/master/benchmark).
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports `asyncio` with proxy rotation on each request.
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

## Install

    pip install curl_cffi --upgrade

This should work on Linux(x86_64/aarch64), macOS(Intel/Apple Silicon) and Windows(amd64).
If it does not work on you platform, you may need to compile and install `curl-impersonate`
first and set some environment variables like `LD_LIBRARY_PATH`.

To install beta releases:

    pip install curl_cffi --pre

## Usage

Use the latest impersonate versions, do NOT copy `chrome110` here without changing.

### requests-like

```python
from curl_cffi import requests

# Notice the impersonate parameter
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110")

print(r.json())
# output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
# the js3n fingerprint should be the same as target browser

# http/socks proxies are supported
proxies = {"https": "http://localhost:3128"}
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)

proxies = {"https": "socks://localhost:3128"}
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110", proxies=proxies)
```

### Sessions

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

Supported impersonate versions, as supported by my [fork](https://github.com/yifeikong/curl-impersonate) of [curl-impersonate](https://github.com/lwthiker/curl-impersonate):

However, only Chrome-like browsers are supported. Firefox support is tracked in #55

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116
- chrome119
- chrome120
- chrome99_android
- edge99
- edge101
- safari15_3
- safari15_5
- safari17_2_ios

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
    "https://googel.com/",
    "https://facebook.com/",
    "https://twitter.com/",
]

async with AsyncSession() as s:
    tasks = []
    for url in urls:
        task = s.get("https://example.com")
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

If you are using scrapy, check out these middlewares:

- [tieyongjie/scrapy-fingerprint](https://github.com/tieyongjie/scrapy-fingerprint)
- [jxlil/scrapy-impersonate](https://github.com/jxlil/scrapy-impersonate)

## Acknowledgement

- Originally forked from [multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), which is under the MIT license.
- Headers/Cookies files are copied from [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), which is under the BSD license.
- Asyncio support is inspired by Tornado's curl http client.
- The WebSocket API is inspired by [websocket_client](https://github.com/websocket-client/websocket-client)

## Sponsor

<a href="https://buymeacoffee.com/yifei" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>
