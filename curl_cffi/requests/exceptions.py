# Apache 2.0 License
# Vendored from https://github.com/psf/requests/blob/main/src/requests/exceptions.py

import json

from .. import CurlError


class RequestsError(CurlError, IOError):
    """Base exception for curl_cffi.requests package, alias of RequestException"""

    def __init__(self, msg, code=0, response=None, *args, **kwargs):
        super().__init__(msg, code, *args, **kwargs)
        self.response = response


class RequestException(RequestsError):
    """Base exception for curl_cffi.requests package."""
    pass


class CookieConflict(RequestException):
    """Same cookie exists for different domains."""
    pass


class SessionClosed(RequestException):
    """The session has already been closed."""
    pass


class InvalidJSONError(RequestException):
    """A JSON error occurred."""
    pass


class JSONDecodeError(InvalidJSONError, json.JSONDecodeError):
    """Couldn't decode the text into json"""
    pass


class HTTPError(RequestException):
    """An HTTP error occurred."""


class ConnectionError(RequestException):
    """A Connection error occurred."""
    pass


class ProxyError(RequestException):
    """A proxy error occurred."""


class SSLError(ConnectionError):
    """An SSL error occurred."""


class Timeout(RequestException):
    """The request timed out."""


class ConnectTimeout(ConnectionError, Timeout):
    """The request timed out while trying to connect to the remote server.

    Requests that produced this error are safe to retry.
    """


class ReadTimeout(Timeout):
    """The server did not send any data in the allotted amount of time."""


class URLRequired(RequestException):
    """A valid URL is required to make a request."""


class TooManyRedirects(RequestException):
    """Too many redirects."""


class MissingSchema(RequestException, ValueError):
    """The URL scheme (e.g. http or https) is missing."""


class InvalidSchema(RequestException, ValueError):
    """The URL scheme provided is either invalid or unsupported."""


class InvalidURL(RequestException, ValueError):
    """The URL provided was somehow invalid."""


class InvalidHeader(RequestException, ValueError):
    """The header value provided was somehow invalid."""


class InvalidProxyURL(InvalidURL):
    """The proxy URL provided is invalid."""


class ChunkedEncodingError(RequestException):
    """The server declared chunked encoding but sent an invalid chunk."""


class ContentDecodingError(RequestException):
    """Failed to decode response content."""


class StreamConsumedError(RequestException, TypeError):
    """The content for this response was already consumed."""


class RetryError(RequestException):
    """Custom retries logic failed"""


class UnrewindableBodyError(RequestException):
    """Requests encountered an error when trying to rewind a body."""


# Warnings


class RequestsWarning(Warning):
    """Base warning for Requests."""


class FileModeWarning(RequestsWarning, DeprecationWarning):
    """A file was opened in text mode, but Requests determined its binary length."""


class RequestsDependencyWarning(RequestsWarning):
    """An imported dependency doesn't match the expected version range."""
