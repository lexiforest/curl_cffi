.. curl_cffi documentation master file, created by
   sphinx-quickstart on Sat Feb 17 22:22:59 2024.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

curl_cffi's documentation
=========================

.. toctree::
   :maxdepth: 2
   :caption: Contents:
   :glob:

   quick_start
   impersonate/_index
   advanced
   vs-requests
   cookies
   community
   api
   faq
   changelog
   dev

`Discuss on Telegram`_

.. _Discuss on Telegram: https://t.me/+lL9n33eZp480MGM1

curl_cffi is a Python binding for `curl-impersonate fork`_ via `cffi`_. For commercial
support, visit `impersonate.pro <https://impersonate.pro>`_.

.. _curl-impersonate fork: https://github.com/lexiforest/curl-impersonate
.. _cffi: https://cffi.readthedocs.io/en/latest/

Unlike other pure Python http clients like ``httpx`` or ``requests``, ``curl_cffi`` can
impersonate browsers' TLS signatures or JA3 fingerprints. If you are blocked by some
website for no obvious reason, you can give this package a try.

If you are looking for Python http3 clients, curl_cffi added http3 support since ``v0.11``.

Sponsors
--------


Bypass Cloudflare with API
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/yescaptcha.png
   :width: 149
   :alt: YesCaptcha
   :target: https://yescaptcha.com/i/stfnIO

`Yescaptcha <https://yescaptcha.com/i/stfnIO>`_ is a proxy service that bypasses Cloudflare and uses the API interface to
obtain verified cookies (e.g. ``cf_clearance``). Click `here <https://yescaptcha.com/i/stfnIO>`_
to register.


You can also click `here <https://buymeacoffee.com/yifei>`_ to buy me a coffee.

Residential Proxies
~~~~~~~~~~~~~~~~~~~

.. image:: https://raw.githubusercontent.com/lexiforest/curl_cffi/main/assets/thordata.png
   :width: 149
   :alt: Thordata
   :target: https://www.thordata.com/?ls=github&lk=curl_cffi

`Thordata <https://www.thordata.com/?ls=github&lk=curl_cffi>`_: A reliable and cost-effective proxy service provider. One-click collection of public network data, providing enterprises and developers with stable, efficient, and compliant global proxy IP services. Register for a free trial of `residential proxies <https://www.thordata.com/products/residential-proxies/?ls=github&lk=curl_cffi>`_ and receive 2000 free SERP API calls.


Features
--------

- Supports JA3/TLS and http2 fingerprints impersonation, including recent browsers and custom fingerprints.
- Much faster than requests/httpx, on par with aiohttp/pycurl, see `benchmarks <https://github.com/lexiforest/curl_cffi/tree/main/benchmark>`_.
- Mimics requests API, no need to learn another one.
- Pre-compiled, so you don't have to compile on your machine.
- Supports ``asyncio`` with proxy rotation on each request.
- Supports http 2.0 & 3.0, which requests does not.
- Supports websocket.

.. list-table:: Feature matrix
   :widths: 20 16 16 16 16 16
   :header-rows: 1

   * - 
     - requests
     - aiohttp
     - httpx
     - pycurl
     - curl_cffi
   * - http2
     - ❌
     - ❌
     - ✅
     - ✅
     - ✅
   * - http3
     - ❌
     - ❌
     - ❌
     - ✅
     - ✅
   * - sync
     - ✅
     - ❌
     - ✅
     - ✅
     - ✅
   * - async
     - ❌
     - ✅
     - ✅
     - ❌
     - ✅
   * - websocket
     - ❌
     - ✅
     - ❌
     - ❌
     - ✅
   * - native retry
     - ❌
     - ❌
     - ❌
     - ❌
     - ✅
   * - fingerprints
     - ❌
     - ❌
     - ❌
     - ❌
     - ✅
   * - speed
     - 🐇
     - 🐇🐇
     - 🐇
     - 🐇🐇
     - 🐇🐇

Notes:

1. For pycurl, you need a http/3 enabled libcurl, while curl_cffi packages libcurl-impersonate inside Python wheels.
2. Full http/3 supported was added in v0.12.0.

Install
-------

.. code-block:: sh

    pip install curl_cffi --upgrade

For more details, see :doc:`quick_start`.

Documentation
-------------

You can first check out :doc:`quick_start`. Then the :doc:`impersonate`.

For advanced topics, checkout :doc:`cookies`, :doc:`asyncio` and :doc:`websockets`.

You can also find common use cases in the `examples <https://github.com/lexiforest/curl_cffi/tree/main/examples>`_ directory.

Finally, if something is missing from the tutorial, you can always find them in the :doc:`api`.

If you have any questions, be sure to check out the :doc:`faq` section before opening an issue.


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
