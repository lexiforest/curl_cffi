# Frequently Asked Questions

## Why does the JA3 fingerprints change for Chrome 110+ impersonation?

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

Or, you can just force curl to use http 1.1 only.

    from curl_cffi import requests, CurlHttpVersion

    r = requests.get("https://postman-echo.com", http_version=CurlHttpVersion.v1_1)
