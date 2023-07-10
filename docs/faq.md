# Frequently Asked Questions

## Pyinstaller `ModuleNotFoundError: No module named '_cffi_backend'`

You need to tell pyinstaller to pack cffi and data files inside the package:

    pyinstaller -F .\example.py --hidden-import=_cffi_backend --collect-all curl_cffi

See also [issue #48](https://github.com/yifeikong/curl_cffi/issues/48) for additional parameters.

## Using https proxy, error: `OPENSSL_internal:WRONG_VERSION_NUMBER`

You are messing up https-over-http proxy and https-over-https proxy, for most cases, you
should change `{"https": "https://localhost:3128"}` to `{"https": "http://localhost:3128"}`.
Note the protocol in the url for https proxy is `http` not `https`.

See [this issue](https://github.com/yifeikong/curl_cffi/issues/6#issuecomment-1415162495)
for a detailed explanation.

## Why does the JA3 fingerprints change for Chrome 110+ impersontation?

This is intended.

Chrome introduces ClientHello permutation in version 110, which means the order of
extensions will be random, thus JA3 fingerprints will be random. So, when comparing
JA3 fingerprints of `curl_cffi` and a browser, they may differ. However, this does not
mean that TLS fingerprints will not be a problem, ClientHello extension order is just
one factor of how servers can tell automated requests from browsers.

Roughly, this can be mitigated like:

    ja3 = md5(list(extensions), ...other arguments)
    ja3n = md5(set(extensions), ...other arguments)


See more from [this article](https://www.fastly.com/blog/a-first-look-at-chromes-tls-clienthello-permutation-in-the-wild)
and [curl-impersonate notes](https://github.com/lwthiker/curl-impersonate/pull/148).

## I'm getting certs errors

The simplest way is to turn off cert verification by `verify=False`:

    r = requests.get("https://example.com", verify=False)

## curl_cffi.CurlError: Failed to perform, ErrCode: 92, Reason: 'HTTP/2 stream 0 was not closed cleanly: PROTOCOL_ERROR (err 1)'

Try remove the `Content-Length` header from you request. see [#19](https://github.com/yifeikong/curl_cffi/issues/19).

## Not working on Windows, `NotImplementedError`

Accroding to the [docs](https://docs.python.org/3/library/asyncio-platforms.html#windows):

> Changed in version 3.8: On Windows, [ProactorEventLoop](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.ProactorEventLoop) is now the default event loop.
> The [loop.add_reader()](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_reader) and [loop.add_writer()](https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.add_writer) methods are not supported.

You can use the SelectorEventLoop instead.

```python
import sys, asyncio

if sys.version_info >= (3, 8) and sys.platform.lower().startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
```

