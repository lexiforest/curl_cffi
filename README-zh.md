# curl_cffi

[curl-impersonate](https://github.com/lwthiker/curl-impersonate) 的 Python 绑定，基于
[cffi](https://cffi.readthedocs.io/en/latest/).

不同于其他的纯 Python http 客户端，比如 `httpx` 和 `requests`，这个库可以模拟浏览器的
TLS 或者 JA3 指纹。如果你莫名其妙地被某个网站封锁了，可以来试试这个库。

## 功能

- 支持 JA3/TLS 和 http2 指纹模拟。
- 比 requests/tls_client 快得多，和 aiohttp/pycurl 的速度比肩，详情查看 [benchmarks](https://github.com/yifeikong/curl_cffi/tree/master/benchmark)。
- 模仿 requests 的 API，不用再学一个新的。
- 预编译，不需要再自己机器上再弄一遍。
- 支持 `asyncio`，并且每个请求都可以换代理。
- 支持 http 2.0，requests 不支持。

## 安装

    pip install curl_cffi --upgrade

在 Linux(x86_64/aarch64), macOS(Intel/Apple Silicon), Windows(amd64), 这样应该就够了，如果
在其他小众平台，你可能需要先编译并安装 `curl-impersonate` 并且设置 `LD_LIBRARY_PATH` 这些
环境变量。

## 使用

### 类 requests

```python
from curl_cffi import requests

# 注意 impersonate 这个参数
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome110")

print(r.json())
# output: {..., "ja3n_hash": "aa56c057ad164ec4fdcb7a5a283be9fc", ...}
# ja3n 指纹和目标浏览器一致

# 支持使用代理
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

支持模拟的浏览器版本，和 [curl-impersonate](https://github.com/lwthiker/curl-impersonate) 一致：

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome99_android
- edge99
- edge101
- safari15_3
- safari15_5

### asyncio

```python
from curl_cffi.requests import AsyncSession

async with AsyncSession() as s:
    r = await s.get("https://example.com")
```

更多并发:

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

### 类 curl

另外，你还可以使用类似 curl 的底层 API：

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

更多细节请查看 [英文文档](https://curl-cffi.readthedocs.io)。

有问题和建议请优先提 issue，中英文均可，也可以加微信群交流讨论：

<img src="wechat.jpg" style="width: 512px;" />

## 致谢

- 该项目 fork 自：[multippt/python_curl_cffi](https://github.com/multippt/python_curl_cffi), MIT 协议发布。
- Headers/Cookies 代码来自 [httpx](https://github.com/encode/httpx/blob/master/httpx/_models.py), BSD 协议发布。
- Asyncio 支持是受 Tornado 的 curl http client 启发而做。
