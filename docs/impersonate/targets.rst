Supported browser impersonate targets
-------------------------------------

``curl_cffi`` supports the same browser versions as supported by our `fork of curl-impersonate <https://github.com/lexiforest/curl-impersonate>`_.

Browser versions will be added **only** when their fingerprints change. If you see a version, e.g.
``chrome122``, was skipped, you can simply impersonate it with your own headers and the previous version.

If you are too busy to look up those details, you can try our commercial version at `impersonate.pro <https://impersonate.pro>`_,
which has a weekly updated list of browser profiles and even more browser types.

If you are trying to impersonate a target other than a browser, use ``ja3=...``, ``akamai=...`` and ``extra_fp=...``
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
- chrome131 :sup:`5`
- chrome133a :sup:`5` :sup:`6`
- chrome136 :sup:`8`
- chrome142 :sup:`11`
- chrome145 :sup:`13` :sup:`14`
- chrome146 :sup:`13` :sup:`14`
- chrome99_android
- chrome131_android :sup:`5`
- edge99
- edge101
- safari153 :sup:`2` :sup:`9`
- safari155 :sup:`2` :sup:`9`
- safari170 :sup:`1` :sup:`9`
- safari172_ios :sup:`1` :sup:`9`
- safari180 :sup:`4` :sup:`9`
- safari180_ios :sup:`4` :sup:`9`
- safari184 :sup:`8` :sup:`9`
- safari184_ios :sup:`8` :sup:`9`
- safari260 :sup:`9` :sup:`10`
- safari260_ios :sup:`9` :sup:`10`
- safari2601 :sup:`9` :sup:`11`
- firefox133 :sup:`5`
- firefox135 :sup:`7`
- firefox144 :sup:`11` :sup:`12`
- firefox147 :sup:`13` :sup:`14`
- tor145 :sup:`8`

Notes:

1. Added in version ``0.6.0``.
2. Fixed in version ``0.6.0``, previous http2 fingerprints were `not correct <https://github.com/lwthiker/curl-impersonate/issues/215>`_.
3. Added in version ``0.7.0``.
4. Added in version ``0.8.0``.
5. Added in version ``0.9.0``.
6. The version suffix ``a`` (e.g. ``chrome133a``) means that this is an alternative version, i.e. the fingerprint has not been officially updated by browser, but has been observed because of A/B testing.
7. Added in version ``0.10.0``.
8. Added in version ``0.11.0``
9. Since ``0.11.0``, the format ``safari184_ios`` is preferred over ``safari18_4_ios``, both are supported, but the latter is quite confusing and hard to parse.
10. Added in version ``0.12.0``
11. Added in version ``0.14.0``.
12. Fixed in version ``0.15.0``, previous User-Agent header was `not correct <https://github.com/lexiforest/curl-impersonate/issues/234>`_.
13. Added in version ``0.15.0``.
14. http3 support included.


Which target version to use?
----------------------------

Generally speaking, you should use the latest Chrome or Safari versions. Currently, they're
``chrome146``, ``safari260`` and ``safari260_ios``. To always impersonate the latest available
browser versions, you can simply use ``chrome``, ``firefox``, ``safari`` and ``chrome_android``, ``safari_ios``.

.. code-block:: python

    import curl_cffi

    curl_cffi.get(url, impersonate="chrome")


Tips:

iOS has restrictions on WebView and TLS libs, so ``safari_*_ios`` should work for a lot of apps.
If you encountered an android app with custom fingerprints, you can try the ``safari_ios``
fingerprints, given that this app should have an iOS version.
