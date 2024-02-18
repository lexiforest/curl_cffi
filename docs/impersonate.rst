Impersonate guide
======

Supported browser versions
--------------------------

Supported impersonate versions, as supported by our [fork](https://github.com/yifeikong/curl-impersonate) of [curl-impersonate](https://github.com/lwthiker/curl-impersonate):

However, only Chrome-like browsers are supported. Firefox support is tracked in [#59](https://github.com/yifeikong/curl_cffi/issues/59).

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116 <sup>[1]</sup>
- chrome119 <sup>[1]</sup>
- chrome120 <sup>[1]</sup>
- chrome99_android
- edge99
- edge101
- safari15_3 <sup>[2]</sup>
- safari15_5 <sup>[2]</sup>
- safari17_0 <sup>[1]</sup>
- safari17_2_ios <sup>[1]</sup>

Notes:
1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were [not correct](https://github.com/lwthiker/curl-impersonate/issues/215).

Which version to use?
---------------------

Generally speaking, you should use the latest Chrome or Safari versions. As of 0.6, they're
``chrome120``, ``safari17_0`` and ``safari17_2_ios``. To always impersonate the latest avaiable
browser versions, you can simply use ``chrome``, ``safari`` and ``safari_ios``.

    from curl_cffi import requests

    requests.get(url, impersonate="chrome")

Should I randomize browser fingerprints, or even change them for each request?
------

The answer is: Yes, and No.

Browser fingerprint does not change for each request. You should not change that, too.
Let's say if you are a website owner, would be block all the Chrome 120 users, that's
almost 10% of all your users.

How to impersonate a custom fingerprint?
------



