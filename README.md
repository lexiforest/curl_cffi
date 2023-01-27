# curl_cffi

Python binding for [curl-impersonate](https://github.com/lwthiker/curl-impersonate)
via [CFFI](https://cffi.readthedocs.io/en/latest/).

Unlike other pure python http clients like `httpx` or `requests`, this package can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

## Install

    pip install --upgrade curl_cffi

This should work for most Linux systems. If it does not work, you may need to compile and
install [curl-impersonate](https://github.com/lwthiker/curl-impersonate) first.

## Usage

`requests/httpx`-like API:

```python
from curl_cffi import requests

# Notice the impersonate parameter
r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101")

print(r.json())
# output: {'ja3_hash': '53ff64ddf993ca882b70e1c82af5da49'
# the fingerprint should be the same as target browser
```

Or, the low-level curl-like API:

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

See `example.py` or `tests/` from more examples.

## API

Requests: almost the same as requests.

Curl object:

* `setopt(CurlOpt, value)`: Sets curl options as in `curl_easy_setopt`
* `perform()`: Performs curl request, as in `curl_easy_perform`
* `getinfo(CurlInfo)`: Gets information in response after curl perform, as in `curl_easy_getinfo`
* `close()`: Closes and cleans up the curl object, as in `curl_easy_cleanup`

Enum values to be used with `setopt` and `getinfo` can be accessed from `CurlOpt` and `CurlInfo`.

## Current Status

This repo is very early stage for now, the pypi package only works on Linux, not macOS
or Windows. If you wish to use it on macOS or Windows, you need to clone it and the
curl-impersonate repo, and then compile them by yourself.

When people installing other python curl bindings, like `pycurl`, they often face
compiling issues or OpenSSL issues, so I really hope that this package can be distributed
as a compiled binary package, uses would be able to use it by a simple `pip install`, no
more compile errors.

For now, I just download the pre-compiled `libcurl-impersonate` from github and build a
bdist wheel, which is a binary package format used by PyPI, and upload it. However, the
right way is to download curl and curl-impersonate sources on our side and compile them
all together.

Help wanted! 

TODOs:

- [ ] write docs.
- [ ] binary package for macOS and Windows.
- [ ] Support musllinux(alpine) bdist by building curl-impersonate from source.
- [ ] Update curl header files and constants via scripts.
- [ ] Implement `requests.Session/httpx.Session`.

## Acknowledgement

This package was originally forked from https://github.com/multippt/python_curl_cffi

