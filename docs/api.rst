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

requests-like API
-----------------

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


.. autoclass:: curl_cffi.requests.TrioSession

   .. automethod:: __init__
   .. automethod:: request
   .. automethod:: stream
   .. automethod:: close

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

Request, Response
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

Asyncio
-------

WebSocket
---------

.. autoclass:: curl_cffi.requests.WebSocket

   .. automethod:: __init__
   .. automethod:: connect
   .. automethod:: recv_fragment
   .. automethod:: recv
   .. automethod:: recv_str
   .. automethod:: recv_json
   .. automethod:: send
   .. automethod:: send_binary
   .. automethod:: send_bytes
   .. automethod:: send_str
   .. automethod:: send_json
   .. automethod:: ping
   .. automethod:: run_forever
   .. automethod:: close

.. autoclass:: curl_cffi.requests.AsyncWebSocket

   .. automethod:: __init__
   .. automethod:: recv_fragment
   .. automethod:: recv
   .. automethod:: recv_str
   .. automethod:: recv_json
   .. automethod:: send
   .. automethod:: send_binary
   .. automethod:: send_bytes
   .. automethod:: send_str
   .. automethod:: send_json
   .. automethod:: ping
   .. automethod:: close

Exceptions and Warnings
-----------------------

Exceptions
~~~~~~~~~~~~~~

We try to follow the `requests` exception hirearchy, however, some are missing, while
some are added.

If an exception is marked as "not used", please catch the base exception.


.. autoclass:: curl_cffi.requests.exceptions.RequestException
.. autoclass:: curl_cffi.requests.exceptions.CookieConflict
.. autoclass:: curl_cffi.requests.exceptions.SessionClosed
.. autoclass:: curl_cffi.requests.exceptions.ImpersonateError
.. autoclass:: curl_cffi.requests.exceptions.InvalidJSONError
.. autoclass:: curl_cffi.requests.exceptions.HTTPError
.. autoclass:: curl_cffi.requests.exceptions.IncompleteRead
.. autoclass:: curl_cffi.requests.exceptions.ConnectionError
.. autoclass:: curl_cffi.requests.exceptions.DNSError
.. autoclass:: curl_cffi.requests.exceptions.ProxyError
.. autoclass:: curl_cffi.requests.exceptions.SSLError
.. autoclass:: curl_cffi.requests.exceptions.CertificateVerifyError
.. autoclass:: curl_cffi.requests.exceptions.Timeout
.. autoclass:: curl_cffi.requests.exceptions.ConnectTimeout
.. autoclass:: curl_cffi.requests.exceptions.ReadTimeout
.. autoclass:: curl_cffi.requests.exceptions.URLRequired
.. autoclass:: curl_cffi.requests.exceptions.TooManyRedirects
.. autoclass:: curl_cffi.requests.exceptions.MissingSchema
.. autoclass:: curl_cffi.requests.exceptions.InvalidSchema
.. autoclass:: curl_cffi.requests.exceptions.InvalidURL
.. autoclass:: curl_cffi.requests.exceptions.InvalidHeader
.. autoclass:: curl_cffi.requests.exceptions.InvalidProxyURL
.. autoclass:: curl_cffi.requests.exceptions.ChunkedEncodingError
.. autoclass:: curl_cffi.requests.exceptions.ContentDecodingError
.. autoclass:: curl_cffi.requests.exceptions.StreamConsumedError
.. autoclass:: curl_cffi.requests.exceptions.RetryError
.. autoclass:: curl_cffi.requests.exceptions.UnrewindableBodyError
.. autoclass:: curl_cffi.requests.exceptions.InterfaceError

Warnings
~~~~~~~~~~~~~~

.. autoclass:: curl_cffi.requests.exceptions.RequestsWarning
.. autoclass:: curl_cffi.requests.exceptions.FileModeWarning
.. autoclass:: curl_cffi.requests.exceptions.RequestsDependencyWarning
