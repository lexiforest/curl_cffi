API References
======

curl low levl APIs
------------------

Curl
~~~~~~

.. autoclass:: curl_cffi.Curl

   .. automethod:: __init__
   .. automethod:: debug
   .. automethod:: setopt
   .. automethod:: getinfo
   .. automethod:: version
   .. automethod:: impersonate
   .. automethod:: perform
   .. automethod:: duphandle
   .. automethod:: reset
   .. automethod:: parse_cookie_headers
   .. automethod:: get_reason_phrase
   .. automethod:: parse_status_line
   .. automethod:: close
   .. automethod:: ws_recv
   .. automethod:: ws_send
   .. automethod:: ws_close

AsyncCurl
~~~~~~

.. autoclass:: curl_cffi.AsyncCurl

   .. automethod:: __init__
   .. automethod:: add_handle
   .. automethod:: remove_handle
   .. automethod:: set_result
   .. automethod:: set_exception
   .. automethod:: setopt
   .. automethod:: socket_action
   .. automethod:: process_data
   .. automethod:: close

CurlMime
~~~~~~

.. autoclass:: curl_cffi.CurlMime

   .. automethod:: __init__
   .. automethod:: addpart
   .. automethod:: from_list
   .. automethod:: attach
   .. automethod:: close

Constants
~~~~~~~~~

Enum values used by ``setopt`` and ``getinfo`` can be accessed from ``CurlOpt`` and
``CurlInfo``.

.. autoclass:: curl_cffi.CurlOpt
.. autoclass:: curl_cffi.CurlInfo
.. autoclass:: curl_cffi.CurlMOpt
.. autoclass:: curl_cffi.CurlECode
.. autoclass:: curl_cffi.CurlHttpVersion
.. autoclass:: curl_cffi.CurlWsFlag
.. autoclass:: curl_cffi.CurlSslVersion

requests API
--------

request method
~~~~~~~~~~~~~~

``requests.get``, ``requests.post``, etc are just aliases of ``.request(METHOD, ...)``

.. autofunction:: curl_cffi.requests.request


Sessions
~~~~~~~

.. autoclass:: curl_cffi.requests.Session

   .. automethod:: __init__
   .. automethod:: request
   .. automethod:: stream
   .. automethod:: ws_connect


.. autoclass:: curl_cffi.requests.AsyncSession

   .. automethod:: __init__
   .. automethod:: request
   .. automethod:: stream
   .. automethod:: close
   .. automethod:: ws_connect

Headers
~~~~~~~

.. autoclass:: curl_cffi.requests.Headers

   .. autoproperty:: encoding
   .. automethod:: raw
   .. automethod:: multi_items
   .. automethod:: get
   .. automethod:: get_list
   .. automethod:: update
   .. automethod:: __getitem__
   .. automethod:: __setitem__
   .. automethod:: __delitem__

Cookies
~~~~~~~

.. autoclass:: curl_cffi.requests.Cookies

   .. automethod:: set
   .. automethod:: get
   .. automethod:: delete
   .. automethod:: clear
   .. automethod:: update
   .. automethod:: __getitem__
   .. automethod:: __setitem__
   .. automethod:: __delitem__

Request, Response and WebSocket
~~~~~~

.. autoclass:: curl_cffi.requests.Request

.. autoclass:: curl_cffi.requests.Response

   .. automethod:: raise_for_status
   .. automethod:: iter_lines
   .. automethod:: iter_content
   .. automethod:: json
   .. automethod:: close
   .. automethod:: aiter_lines
   .. automethod:: aiter_content
   .. automethod:: atext
   .. automethod:: acontent
   .. automethod:: aclose

.. autoclass:: curl_cffi.requests.WebSocket

   .. automethod:: __init__
   .. automethod:: recv
   .. automethod:: send
   .. automethod:: run_forever
   .. automethod:: close
   .. automethod:: arecv
   .. automethod:: asend

