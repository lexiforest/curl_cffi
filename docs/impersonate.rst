Impersonate guide
======

Supported browser versions
--------------------------

``curl_cffi`` supports the same browser versions as supported by our `fork <https://github.com/lexiforest/curl-impersonate>`_ of `curl-impersonate <https://github.com/lwthiker/curl-impersonate>`_:

However, only Chrome-like browsers are supported. Firefox support is tracked in `#59 <https://github.com/lexiforest/curl_cffi/issues/59>`_.

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
- chrome131 :sup:`4`
- chrome133a :sup:`5` :sup:`6`
- chrome136 :sup:`7`
- chrome99_android
- chrome131_android :sup:`4`
- edge99
- edge101
- safari153 :sup:`2`
- safari155 :sup:`2`
- safari170 :sup:`1`
- safari172_ios :sup:`1`
- safari180 :sup:`4`
- safari180_ios :sup:`4`
- safari184 :sup:`7`
- safari184_ios :sup:`7`
- firefox133 :sup:`5`
- tor145 :sup:`7`

Notes:

1. Added in version `0.6.0`.
2. Fixed in version `0.6.0`, previous http2 fingerprints were `not correct <https://github.com/lwthiker/curl-impersonate/issues/215>`_.
3. Added in version `0.7.0`.
4. Added in version `0.8.0`.
5. Added in version `0.9.0`.
6. The version postfix `-a`(e.g. `chrome133a`) means that this is an alternative version, i.e. the fingerprint has not been officially updated by browser, but has been observed because of A/B testing.
7. Added in version `0.11.0`

Which version to use?
---------------------

Generally speaking, you should use the latest Chrome or Safari versions. As of 0.7, they're
``chrome124``, ``safari17_0`` and ``safari17_2_ios``. To always impersonate the latest avaiable
browser versions, you can simply use ``chrome``, ``safari`` and ``safari_ios``.

.. code-block:: python

    import curl_cffi

    curl_cffi.get(url, impersonate="chrome")

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


   r = curl_cffi.get(
       url, ja3=okhttp4_android10_ja3, akamai=okhttp4_android10_akamai, extra_fp=extra_fp
   )
   print(r.json())


There are a few special extensions from firefox that you add extra options by ``extra_fp``:

Extension 34: delegated credentials

.. code-block:: python

   extra_fp = {
       "tls_delegated_credential": "ecdsa_secp256r1_sha256:ecdsa_secp384r1_sha384:ecdsa_secp521r1_sha512:ecdsa_sha1"
   }

   # Note that the ja3 string also includes extensiion: 34
   ja3 = "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-34-18-51-43-13-45-28-27-65037,4588-29-23-24-25-256-257,0"

   r = curl_cffi.get(url, ja3=ja3, extra_fp=extra_fp)

Extension 28: record size limit

.. code-block:: python

   extra_fp = {
       "tls_record_size_limit": 4001
   }

   # Note that the ja3 string also includes extensiion: 28
   ja3 = "771,4865-4867-4866-49195-49199-52393-52392-49196-49200-49162-49161-49171-49172-156-157-47-53,0-23-65281-10-11-35-16-5-34-18-51-43-13-45-28-27-65037,4588-29-23-24-25-256-257,0"

   r = curl_cffi.get(url, ja3=ja3, extra_fp=extra_fp)


JA3 and Akamai String Format
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A JA3 string is a simple, comma-separated representation of the key fields in a TLS ClientHello. It consists of five parts:

- SSL/TLS Version, The numeric version the client requests (e.g. 771 for TLS 1.2).
- Cipher Suites, A hyphen-separated list of all cipher suite IDs offered by the client (e.g. 4865-4866-4867-49195-49196).
- Extension IDs, A hyphen-separated list of all TLS extension numbers the client includes (e.g. 0-11-10-35-16-5).
- Supported Groups (aka “Elliptic Curves”), A hyphen-separated list of curve IDs the client supports for ECDHE (e.g. 29-23-24).
- EC Point Formats, A hyphen-separated list of the point‐format IDs (almost always just 0 for “uncompressed”) (e.g. 0).

They’re concatenated in that exact order, with commas between fields. For example:

.. code-block::

    771,4865-4866-4867-49195-49196,0-11-10-35-16-5,29-23-24,0

Note that Chrome permutes the extension order on each request, so there is a new format called JA3N, which uses sorted extension_id list.

The Akamai HTTP/2 fingerprint string encodes four client‐controlled protocol parameters, joined by the pipe character (|):

- SETTINGS, A semicolon‐separated list of ID:value pairs from the client’s initial SETTINGS frame. Each ID is a standard HTTP/2 setting identifier (e.g. 1 for HEADER_TABLE_SIZE, 4 for INITIAL_WINDOW_SIZE), and value is the client’s chosen value for that setting 
- WINDOW_UPDATE, A single integer: the value the client sends in its first WINDOW_UPDATE frame (or 0 if none was sent) 
- PRIORITY, Zero or more priority‐frame tuples, each formatted as ``StreamID:ExclusiveBit:DependentStreamID:Weight``. Multiple tuples are comma-separated. This captures any PRIORITY frames the client issues before sending headers 
- Pseudo-Header Order, The sequence in which the client sends HTTP/2 pseudo-headers in its request HEADERS frame, encoded as comma-separated single-letter codes:


.. code-block::
    m = :method
    s = :scheme
    p = :path
    a = :authority

Putting it all together, an example fingerprint might look like:

.. code-block::

    1:65536;4:131072;5:16384|12517377|3:0:0:201|m,p,a,s

    where:

    SETTINGS = 1:65536;4:131072;5:16384
    WINDOW_UPDATE = 12517377
    PRIORITY = 3:0:0:201
    Pseudo-Header Order = m,p,a,s 

Although JA3 and Akamai fingerprint string already captures many of the aspects of a Hello Packet, there are still some fields are not covered and can be used to detect you.
This is when the ``extra_fp`` option comes in, each field of this dict is pretty easy to understand. You should first set the ja3 and akamai string, then check if you have the
identical fingerprint like your target. If not, use the ``extra_fp`` to further refine your impersonation.



Using CURLOPTs
~~~~~~~~~~~~~~

The other way is to use the ``curlopt`` s to specify exactly which options you want to change.

To modify them, use ``curl.setopt(CurlOpt, value)``, for example:

.. code-block:: python

   import curl_cffi
   from curl_cffi import Curl, CurlOpt

   c = Curl()
   c.setopt(CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER, "masp")

   # or
   curl_cffi.get(url, curl_options={CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER, "masp"})

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

* ``CURLOPT_HTTP2_PSEUDO_HEADERS_ORDER``, sets http2 pseudo header order, for example: ``masp`` (non-standard HTTP/2 options created for this project).
* ``CURLOPT_HTTP2_SETTINGS`` sets the settings frame values, for example ``1:65536;3:1000;4:6291456;6:262144`` (non-standard HTTP/2 options created for this project).
* ``CURLOPT_HTTP2_WINDOW_UPDATE`` sets initial window update value for http2, for example ``15663105`` (non-standard HTTP/2 options created for this project).

For a complete list of options and explanation, see the `curl-impersoante README`_.

.. _curl-impersonate README: https://github.com/lexiforest/curl-impersonate?tab=readme-ov-file#libcurl-impersonate


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
