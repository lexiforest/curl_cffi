FAQ
==========================

Why does the JA3 fingerprints change for Chrome 110+ impersonation?
------

This is intended.

Chrome introduces ``ClientHello`` permutation in version 110, which means the order of
extensions will be random, thus JA3 fingerprints will be random. So, when comparing
JA3 fingerprints of ``curl_cffi`` and a browser, they may differ. However, this does not
mean that TLS fingerprints will not be a problem, ``ClientHello`` extension order is just
one factor of how servers can tell automated requests from browsers.

Roughly, this can be mitigated like:

.. code-block::

    ja3 = md5(list(extensions), ...other arguments)
    ja3n = md5(set(extensions), ...other arguments)

See more from `this article <https://www.fastly.com/blog/a-first-look-at-chromes-tls-clienthello-permutation-in-the-wild>`_
and `curl-impersonate notes <https://github.com/lwthiker/curl-impersonate/pull/148>`_.

Can I bypass Cloudflare with this project? or any other specific site.
------

Short answer is: it depends.

TLS and http2 fingerprints are just one of the many factors Cloudflare considers. Other
factors include but are not limited to: IP quality, request rate, JS fingerprints, etc.

There are different protection levels for website owners to choose. For the most basic
ones, TLS fingerprints alone maybe enough, but for higher levels, you may need to find
a better proxy IP provider and use browser automation tools like playwright.

If you are in a hurry or just want the professionals to take care of the hard parts,
you can consider the commercial solutions from our sponsors:

- `Scrapfly <https://scrapfly.io/?utm_source=github&utm_medium=sponsoring&utm_campaign=curl_cffi>`_, Cloud-based scraping platform.
- `Yescaptcha <https://yescaptcha.com/i/stfnIO>`_, captcha resolver and proxy service for bypassing Cloudflare.
- `ScrapeNinja <https://scrapeninja.net/?utm_source=github&utm_medium=banner&utm_campaign=cffi>`_, Managed web scraping API.

For details, see the `Sponsor` section on front page.


I'm getting certs errors
------

The simplest way is to turn off cert verification by ``verify=False``:

.. code-block:: python

    r = requests.get("https://example.com", verify=False)


ErrCode: 77, Reason: error setting certificate verify locations
------

Install ``curl_cffi`` and its dependencies in a pure-ASCII path, i.e. no Chinese or any
other characters out of the ASCII table in the path.


How to use with fiddler/charles to intercept content
------

Fiddler and Charles uses man-in-the-middle self-signed certs to intercept TLS traffic,
to use with them, simply set ``verify=False``.


ErrCode: 92, Reason: 'HTTP/2 stream 0 was not closed cleanly: PROTOCOL_ERROR (err 1)'
------

This error(http/2 stream 0) has been reported many times ever since `curl_cffi` was
published, but I still can not find a reproducible way to trigger it. Given that the
majority users are behind proxies, the situation is even more difficult to deal with.

I'm even not sure it's a bug introduced in libcurl, curl-impersonate or curl_cffi, or
it's just a server error. Depending on your context, here are some general suggestions
for you:

- First, try removing the ``Content-Length`` header from you request.
- Try to see if this error was caused by proxies, if so, use better proxies.
- If it stops working after a while, maybe you're just being blocked by, such as, Akamai.
- Force http/1.1 mode. Some websites' h2 implementation is simply broken.
- See if the url works in your real browser.
- Find a stable way to reproduce it, so we can finally fix, or at least bypass it.

To force curl to use http 1.1 only.

.. code-block:: python

    from curl_cffi import requests, CurlHttpVersion

    r = requests.get("https://postman-echo.com", http_version=CurlHttpVersion.V1_1)

Related issues:

- `#19 <https://github.com/lexiforest/curl_cffi/issues/19>`_, 
- `#42 <https://github.com/lexiforest/curl_cffi/issues/42>`_, 
- `#79 <https://github.com/lexiforest/curl_cffi/issues/79>`_, 
- `#165 <https://github.com/lexiforest/curl_cffi/issues/165>`_, 


Packaging with PyInstaller
------

If you encountered any issue with PyInstaller, here are a list of options provided by the
community:

Add the ``--hidden-import`` option.

.. code-block::

   pyinstaller -F .\example.py --hidden-import=_cffi_backend --collect-all curl_cffi

Add other paths:

.. code-block::

   pyinstaller --noconfirm --onefile --console \
       --paths "C:/Users/Administrator/AppData/Local/Programs/Python/Python39" \
       --add-data "C:/Users/Administrator/AppData/Local/Programs/Python/Python39/Lib/site-packages/curl_cffi.libs/libcurl-cbb416caa1dd01638554eab3f38d682d.dll;." \
       --collect-data "curl_cffi" \
       "C:/Users/Administrator/Desktop/test_script.py"


See also: 

- `#5 <https://github.com/lexiforest/curl_cffi/issues/5>`_
- `#48 <https://github.com/lexiforest/curl_cffi/issues/48>`_

How to set proxy?
------

You can use the ``proxy`` parameter:

.. code-block:: python

    from curl_cffi import requests

    requests.get(url, proxy="http://user:pass@example.com:3128")

You can also use the ``http_proxy``, ``https_proxy``, and ``ws_proxy``, ``wss_proxy``
environment variables, respectively.

For explanation of differences between ``http_proxy`` and ``https_proxy``, please see
`#6 <https://github.com/lexiforest/curl_cffi/issues/6>`_.


How to change the order of headers?
------

By default, setting ``impersonate`` parameter will bring the corresponding headers. If
you want to change the order or use your own headers, you need to turn off that and bring
your own headers.

.. code-block::

   requests.get(url, impersonate="chrome", default_headers=False, headers=...)


How to deal with encoding/decoding errors?

Use ``chardet`` or ``cchardet``

.. code-block::

    >>> from curl_cffi import requests
    >>> r = requests.get("https://example.com/messy_codec.html")
    >>> import chardet
    >>> chardet.detect(r.content)
    {'encoding': 'GB2312', 'confidence': 0.99, 'language': 'Chinese'}

Or use regex or lxml to parse the meta header:

.. code-block::

    <meta http-equiv="Content-Type" content="text/html; charset=gbk" />
