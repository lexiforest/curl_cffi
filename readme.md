# curl_cffi

Python binding for [curl-impersonate](https://github.com/lwthiker/curl-impersonate)
via CFFI.

Unlike pure python http clients like httpx or requests, this package can impersonate
browsers' TLS signatures or JA3 fingerprints.

## Install

    pip install curl_cffi

This should work for most systems. If it does not work, you may need to compile and
install [curl-impersonate](https://github.com/lwthiker/curl-impersonate) first.

## Usage

`requests/httpx`-like API:

```python
from curl_cffi import requests

r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101")
print(r.json())
```

Or, the low-level curl-like API:

```python
from curl_cffi import Curl
from io import BytesIO

buffer = BytesIO()
c = Curl()
c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
c.setopt(CurlOpt.WRITEDATA, buffer)
c.perform()
c.close()
body = buffer.getvalue()
print(body.decode())
```

## API

Curl object:

* `setopt(CurlOpt, value)`: Sets curl options as in `curl_easy_setopt`
* `perform()`: Performs curl request, as in `curl_easy_perform`
* `getinfo(CurlInfo)`: Gets information in response after curl perform, as in `curl_easy_getinfo`
* `close()`: Closes and cleans up the curl object, as in `curl_easy_cleanup`

Enum values to be used with `setopt` and `getinfo` can be accessed from `CurlOpt` and `CurlInfo`.

## TODO

Help wanted!

- [ ] Support musllinux(alpine) bdist by building curl-impersonate from source.
- [ ] Update curl/consts via scripts.
- [ ] Implement `requests.Client/Session`.

## Acknowledgement

This package is originally forked from https://github.com/multippt/python_curl_cffi

