Impersonate guide
======

Supported browser versions
--------------------------

``curl_cffi`` supports the same browser versions as supported by our `fork <https://github.com/yifeikong/curl-impersonate>`_ of `curl-impersonate <https://github.com/lwthiker/curl-impersonate>`_:

However, only Chrome-like browsers are supported. Firefox support is tracked in `#59 <https://github.com/yifeikong/curl_cffi/issues/59>`_.

Browser versions will be added **only** when their fingerprints change. If you see a version, e.g.
chrome122, were skipped, you can simply impersonate it with your own headers and the previous version.

If you are trying to impersonate a target other than a browser, use ``ja3=...`` and ``akamai=...``
to specify your own customized fingerprints. See below for details.

- chrome99
- chrome100
- chrome101
- chrome104
- chrome107
- chrome110
- chrome116 :sup:`1`
- chrome119 :sup:`1`
- chrome120 :sup:`1`
- chrome123 :sup:`3`
- chrome124 :sup:`3`
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
3. Added in version `0.7.0`.

Which version to use?
---------------------

Generally speaking, you should use the latest Chrome or Safari versions. As of 0.7, they're
``chrome124``, ``safari17_0`` and ``safari17_2_ios``. To always impersonate the latest avaiable
browser versions, you can simply use ``chrome``, ``safari`` and ``safari_ios``.

.. code-block:: python

    from curl_cffi import requests

    requests.get(url, impersonate="chrome")

iOS has restrictions on WebView and TLS libs, so ``safari_x_ios`` should work for most apps.
If you encountered an android app with custom fingerprints, you can try the ``safari_ios``
fingerprints given that this app should have an iOS version.

How to use my own fingerprints other than the builtin ones? e.g. okhttp
------

Use ``ja3=...``, ``akamai=...`` and ``extra_fp=...``.

You can retrieve the JA3 and Akamai strings using tools like WireShark or from TLS fingerprinting sites.

.. code-block:: python

   # OKHTTP impersonatation examples
   # credits: https://github.com/bogdanfinn/tls-client/blob/master/profiles/contributed_custom_profiles.go

   url = "https://tls.browserleaks.com/json"

   okhttp4_android10_ja3 = ",".join(
       [
           "771",
           "4865-4866-4867-49195-49196-52393-49199-49200-52392-49171-49172-156-157-47-53",
           "0-23-65281-10-11-35-16-5-13-51-45-43-21",
           "29-23-24",
           "0",
       ]
   )

   okhttp4_android10_akamai = "4:16777216|16711681|0|m,p,a,s"

   extra_fp = {
       "tls_signature_algorithms": [
           "ecdsa_secp256r1_sha256",
           "rsa_pss_rsae_sha256",
           "rsa_pkcs1_sha256",
           "ecdsa_secp384r1_sha384",
           "rsa_pss_rsae_sha384",
           "rsa_pkcs1_sha384",
           "rsa_pss_rsae_sha512",
           "rsa_pkcs1_sha512",
           "rsa_pkcs1_sha1",
       ]
       # other options:
       # tls_min_version: int = CurlSslVersion.TLSv1_2
       # tls_grease: bool = False
       # tls_permute_extensions: bool = False
       # tls_cert_compression: Literal["zlib", "brotli"] = "brotli"
       # tls_signature_algorithms: Optional[List[str]] = None
       # http2_stream_weight: int = 256
       # http2_stream_exclusive: int = 1

       # See requests/impersonate.py and tests/unittest/test_impersonate.py for more examples
   }


   r = requests.get(
       url, ja3=okhttp4_android10_ja3, akamai=okhttp4_android10_akamai, extra_fp=extra_fp
   )
   print(r.json())

The other way is to use the ``curlopt`` s to specify exactly which options you want to change.

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

For a complete list of options and explanation, see the `curl-impersoante README`_.

.. _curl-impersonate README: https://github.com/yifeikong/curl-impersonate?tab=readme-ov-file#libcurl-impersonate


Should I randomize my fingerprints for each request?
------

You can choose a random version from the list above, like:

.. code-block:: python

    random.choice(["chrome119", "chrome120", ...])

However, be aware of the browser market share, very old versions are not good choices.

Generally, you should not try to generate a customized random fingerprints. The reason
is that, for a given browser version, the fingerprints are fixed. If you create a new
random fingerprints, the server is easy to know that you are not using a typical browser.

If you were thinking about ``ja3``, and not ``ja3n``, then the fingerprints is already
randomized, due to the ``extension permutation`` feature introduced in Chrome 110.

As far as we know, most websites use an allowlist, not a blocklist to filter out bot
traffic. So do not expect random ja3 fingerprints would work in the wild.

Moreover, do not generate random ja3 strings. There are certain limits for a valid ja3 string.
For example:

* TLS 1.3 ciphers must be at the front.
* GREASE extension must be the first.
* etc.

You should copy ja3 strings from sniffing tools, not generate them, unless you can make
sure all the requirements are met.

Can I change JavaScript fingerprints with this library?
------

No, you can not. As the name suggests, JavaScript fingerprints are generated using JavaScript
APIs provided by real browsers. ``curl_cffi`` is a python binding to a C library, with no
browser or JavaScript runtime under the hood.

If you need to impersonate browsers on the JavaScript perspective, you can search for
"Anti-detect Browser", "Playwright stealth" and similar keywords. Or simply use a
commercial plan from our sponsors.
