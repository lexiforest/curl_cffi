Exceptions
=======


We try to follow the `requests` exception hirearchy, however, some are missing, while
some are added.

If an exception is marked as "not used", please catch the base exception.


Exceptions
~~~~~~~~~~~~~~


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
