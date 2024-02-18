# for compatibility with 0.5.x

__all__ = ["CurlError", "RequestsError", "CookieConflict", "SessionClosed"]

from .. import CurlError

from .exceptions import RequestsError, CookieConflict, SessionClosed
