Impersonate guide
======

Supported browser versions
--------------------------

Supported impersonate versions, as supported by our `fork <https://github.com/yifeikong/curl-impersonate>`_ of `curl-impersonate <https://github.com/lwthiker/curl-impersonate>`_:

However, only Chrome-like browsers are supported. Firefox support is tracked in `#59 <https://github.com/yifeikong/curl_cffi/issues/59>`_.

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116 :sup:`1`
- chrome119 :sup:`1`
- chrome120 :sup:`1`
- chrome99_android
- edge99
- edge101
- safari15_3 :sup:`2`
- safari15_5 :sup:`2`
- safari17_0 :sup:`1`
- safari17_2_ios :sup:`1`

Notes:

1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were `not correct <https://github.com/lwthiker/curl-impersonate/issues/215>`_.

Which version to use?
---------------------

Generally speaking, you should use the latest Chrome or Safari versions. As of 0.6, they're
``chrome120``, ``safari17_0`` and ``safari17_2_ios``. To always impersonate the latest avaiable
browser versions, you can simply use ``chrome``, ``safari`` and ``safari_ios``.

.. code-block:: python

    from curl_cffi import requests

    requests.get(url, impersonate="chrome")

iOS has restrictions on WebView and TLS libs, so safari_x_ios should work for most apps.
If you encountered an android app with custom fingerprints, you can try the ``safari ios``
fingerprints given that this app should have an iOS version.

How to customize my fingerprints? e.g. okhttp
------

It's not fully implemented, yet.

There are many parts in the JA3 and Akamai http2 fingerprints. Some of them can be changed,
while some can not be changed at the moment. The progress is tracked in https://github.com/yifeikong/curl_cffi/issues/194.

To modify them, use ``curl.setopt(CurlOpt, value)``, for example:

.. code-block:: python

   from curl_cffi import Curl, CurlOpt, requests

   c = Curl()
   c.setopt(CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER, "masp")

   # or
   requests.get(url, curl_options={CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER, "masp"})

Here are a list of options:

For TLS/JA3 fingerprints:

* https://curl.se/libcurl/c/CURLOPT_SSL_CIPHER_LIST.html

and non-standard TLS options created for this project:

* ``CURLOPT_SSL_ENABLE_ALPS``
* ``CURLOPT_SSL_SIG_HASH_ALGS``
* ``CURLOPT_SSL_CERT_COMPRESSION``
* ``CURLOPT_SSL_ENABLE_TICKET``
* ``CURLOPT_SSL_PERMUTE_EXTENSIONS``

For Akamai http2 fingerprints, you can fully customize the 3 parts:

* ``CURLOPT_HTTP2_PSEUDO_HEADERS_ORDER``, sets http2 pseudo header order, for example: `masp` (non-standard HTTP/2 options created for this project).
* ``CURLOPT_HTTP2_SETTINGS`` sets the settings frame values, for example `1:65536;3:1000;4:6291456;6:262144` (non-standard HTTP/2 options created for this project).
* ``CURLOPT_HTTP2_WINDOW_UPDATE`` sets intial window update value for http2, for example `15663105` (non-standard HTTP/2 options created for this project).


Should I randomize my fingerprints for each request?
------

You can use a random from the list above, like:

.. code-block:: python

    random.choice(["chrome119", "chrome120", ...])

However, be aware of the browser market share, very old versions are not good choices.

Generally, you should not try to generate a customized random fingerprints. The reason
is that, for a given browser version, the fingerprints are fixed. If you create a new
random fingerprints, the server is easy to know that you are not using a typical browser.

If you were thinking about ``ja3``, and not ``ja3n``, then the fingerprints is already
randomized, due to the ``extension permutation`` feature introduced in Chrome 110.

AFAIK, most websites use an allowlist, not a blocklist to filter out bot traffic. So I
don’t think random ja3 fingerprints would work in the wild.
