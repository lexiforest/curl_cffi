Community
=========

Scrapy integrations
------

If you are using scrapy, check out these download handlers:

- [divtiply/scrapy-curl-cffi](https://github.com/divtiply/scrapy-curl-cffi)
- [tieyongjie/scrapy-fingerprint](https://github.com/tieyongjie/scrapy-fingerprint)
- [jxlil/scrapy-impersonate](https://github.com/jxlil/scrapy-impersonate)


Using with eventlet/gevent
------

Just set ``thread`` to eventlet or gevent.

.. code-block:: python

   from curl_cffi import requests

   s = requests.Session(thread="eventlet")
   s.get(url)


As a urllib3/requests adapter
------

You can also use curl-cffi as a requests adapter via `curl-adapter <https://github.com/el1s7/curl-adapter>`_.
In this way, you get the full functionality of requests.

.. code-block:: python

   import requests
   from curl_adapter import CurlCffiAdapter

   session = requests.Session()
   session.mount("http://", CurlCffiAdapter())
   session.mount("https://", CurlCffiAdapter())

   # just use requests session like you normally would
   session.get("https://example.com")


As a httpx transport
------

You can also use curl-cffi as a httpx transport via `httpx-curl-cffi <https://github.com/vgavro/httpx-curl-cffi>`_.
With this, you get the full functionality of httpx.

.. code-block:: python

   from httpx import Client, AsyncClient
   from httpx_curl_cffi import CurlTransport, AsyncCurlTransport, CurlOpt

   client = Client(transport=CurlTransport(impersonate="chrome", default_headers=True))
   client.get("https://tools.scrapfly.io/api/fp/ja3")

   async_client = AsyncClient(transport=AsyncCurlTransport(
       impersonate="chrome",
       default_headers=True,
       # required for parallel requests, see curl_cffi issues below
       curl_options={CurlOpt.FRESH_CONNECT: True}
   ))


