Advanced Usage
==============

low-level curl API
---------

Alternatively, you can use the low-level curl-like API:

.. code-block:: python

    from curl_cffi import Curl, CurlOpt
    from io import BytesIO

    buffer = BytesIO()
    c = Curl()
    c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
    c.setopt(CurlOpt.WRITEDATA, buffer)

    c.impersonate("chrome120")

    c.perform()
    c.close()
    body = buffer.getvalue()
    print(body.decode())


scrapy integrations
------

If you are using scrapy, check out these middlewares:

- [tieyongjie/scrapy-fingerprint](https://github.com/tieyongjie/scrapy-fingerprint)
- [jxlil/scrapy-impersonate](https://github.com/jxlil/scrapy-impersonate)


Using with eventlet/gevent
------

Just set ``thread`` to eventlet or gevent.

.. code-block:: python

   from curl_cffi import requests

   s = requests.Session(thread="eventlet")
   s.get(url)
