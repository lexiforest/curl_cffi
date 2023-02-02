# curl_cffi

[curl-impersonate](https://github.com/lwthiker/curl-impersonate) 的 Python 绑定，基于
[CFFI](https://cffi.readthedocs.io/en/latest/).

不同于其他的纯 Python http 客户端，比如 `httpx` 和 `requests`，这个库可以模拟浏览器的
TLS 或者 JA3 指纹。如果你莫名其妙地被某个网站封锁了，可以来试试这个库。

## 安装

    pip install --upgrade curl_cffi

在 Linux(x86_64/aarch64), macOS(Intel), Windows(amd64), 这样应该就够了，如果不工作，你
可能需要先编译并安装 `curl-impersonate`.

## 使用

类 `requests/httpx` API:

```python
from curl_cffi import requests

# 注意 impersonate 这个参数
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101")

print(r.json())
# output: {'ja3_hash': '53ff64ddf993ca882b70e1c82af5da49'
# 指纹和目标浏览器一致

# 支持使用代理
proxies = {"https": "http://localhost:3128"}
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101", proxies=proxies)
```

要查看支持模拟的浏览器的版本列表，请参阅 curl-impersonate 的仓库。

另外，你还可以使用类似 curl 的底层 API：

```python
from curl_cffi import Curl, CurlOpt
from io import BytesIO

buffer = BytesIO()
c = Curl()
c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
c.setopt(CurlOpt.WRITEDATA, buffer)

c.impersonate("chrome101")

c.perform()
c.close()
body = buffer.getvalue()
print(body.decode())
```

查看 `example.py` 或 `tests/` 来了解更多例子。

## API

Requests: 几乎和 requests 相同的 API

Curl 对象：

* `setopt(CurlOpt, value)`: 对应 `curl_easy_setopt`, 设定选项
* `perform()`: 发送 curl 请求，对应 `curl_easy_perform`
* `getinfo(CurlInfo)`: 在 perform 之后读取信息，对应 `curl_easy_getinfo`
* `close()`: 关闭并清理 curl 对象，对应 `curl_easy_cleanup`

在 `setopt` 以及 `getinfo` 用到的枚举值，可以从 `CurlOpt` 和 `CurlInfo` 中读取。

## 疑难问题

### Pyinstaller `ModuleNotFoundError: No module named '_cffi_backend'`

需要指定 pyinstaller 打包 cffi 和数据文件：

    pyinstaller -F .\example.py --hidden-import=_cffi_backend --collect-all curl_cffi

## 项目现状

现在的实现挺 hacky 的，不过在大多数系统上都是可以工作的。

当我安装其他 python 的 curl 绑定时，比如 pycurl，经常会遇到编译问题或者 OpenSSL 的问题，
所以我特别希望有一个二进制分发的包，用户可以直接 `pip install`, 而不会有编译错误。

现在，我只是把别人编译好 `libcurl-impersonate` 库从 github 上下载下来然后编译了一个 bdist
wheel 包，然后上传到 PyPI 上。但是，正确的方式应该是下载 curl 和 curl-impersonate 的源码
并一起从头编译。

需要帮助啊！

TODOs:

- [ ] 写文档
- [x] macOS(Intel) 和 Windows 的二进制包。
- [ ] 支持 musllinux(alpine) 和 macOS(Apple Silicon) bdist， 通过从源码构建。
- [ ] 从源码中删除 curl 头文件，编译的时候再下载。
- [x] 通过脚本更新 curl 常量。
- [ ] 实现 `requests.Session/httpx.Session`.
- [ ] 创建 [ABI3 wheels](https://cibuildwheel.readthedocs.io/en/stable/faq/#abi3) 以减小包的体积和构建时间。

有问题和建议可以加微信群交流讨论：

<img src="wechat.jpg" style="width: 512px;" />

## 致谢

该项目 fork 自：https://github.com/multippt/python_curl_cffi

