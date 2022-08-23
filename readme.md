# Python Curl CFFI

CFFI bindings for libcurl with the ability to impersonate browsers' TLS signatures.

## Install

    pip install curl_cffi

## Usage

```python
from curl_cffi import Curl, CurlOpt, CurlInfo
from io import BytesIO

buffer = BytesIO()
c = Curl()
c.setopt(CurlOpt.URL, b'https://ja3er.com/json')
c.setopt(CurlOpt.WRITEDATA, buffer)
c.perform()
c.close()
body = buffer.getvalue()
print(body.decode())
```

## API

Curl object:

* setopt(CurlOpt, value): Sets curl options as in `curl_easy_setopt`
* perform(): Performs curl request, as in `curl_easy_perform`
* getinfo(CurlInfo): Gets information in response after curl perform, as in `curl_easy_getinfo`
* close(): Closes and cleans up the curl object, as in `curl_easy_cleanup`

Enum values to be used with `setopt` and `getinfo` can be accessed from `CurlOpt` and `CurlInfo`.

## Acknowledgement

This module is forked from https://github.com/multippt/python_curl_cffi
