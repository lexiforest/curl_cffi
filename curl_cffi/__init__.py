__all__ = [
    "Curl",
    "AsyncCurl",
    "CurlMime",
    "CurlError",
    "CurlInfo",
    "CurlOpt",
    "CurlMOpt",
    "CurlECode",
    "CurlHttpVersion",
    "CurlFollow",
    "CurlSslVersion",
    "CurlWsFlag",
    "config_warnings",
    "Fingerprint",
    "FingerprintManager",
    "get_fingerprint",
    "ffi",
    "lib",
    "Session",
    "AsyncSession",
    "BrowserType",
    "BrowserTypeLiteral",
    "request",
    "head",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "Cookies",
    "Headers",
    "Request",
    "Response",
    "AsyncWebSocket",
    "WebSocket",
    "WebSocketError",
    "WebSocketClosed",
    "WebSocketTimeout",
    "WebSocketRetryStrategy",
    "WsCloseCode",
    "ExtraFingerprints",
    "CacheBackend",
    "FileCacheBackend",
    "CookieTypes",
    "HeaderTypes",
    "ProxySpec",
    "exceptions",
]

# flake8: noqa: E402
# The RTLD_DEEPBIND setup below runs before the rest of this file's imports
# by necessity (it must wrap the first import that touches _wrapper), which
# pushes every import after it out of flake8's "top of file" rule.
import os
import sys

import _cffi_backend  # noqa: F401  # required by _wrapper

# Use RTLD_DEEPBIND to prevent BoringSSL symbol collisions with host OpenSSL.
# Must wrap __version__ import as it resolves curl version and loads _wrapper.
_prev_dlopen_flags = None
if hasattr(sys, "setdlopenflags") and hasattr(os, "RTLD_DEEPBIND"):
    _prev_dlopen_flags = sys.getdlopenflags()
    sys.setdlopenflags(os.RTLD_NOW | os.RTLD_DEEPBIND)

try:
    from .__version__ import (  # noqa: F401
        __curl_version__,
        __description__,
        __title__,
        __version__,
    )

    # This line includes _wrapper.so into the wheel
    from ._wrapper import ffi, lib
finally:
    if _prev_dlopen_flags is not None:
        sys.setdlopenflags(_prev_dlopen_flags)
from .aio import AsyncCurl
from .const import (
    CurlECode,
    CurlFollow,
    CurlHttpVersion,
    CurlInfo,
    CurlMOpt,
    CurlOpt,
    CurlSslVersion,
    CurlWsFlag,
)
from .curl import Curl, CurlError, CurlMime

from .requests import (
    AsyncSession,
    AsyncWebSocket,
    BrowserType,
    BrowserTypeLiteral,
    CacheBackend,
    Cookies,
    CookieTypes,
    ExtraFingerprints,
    FileCacheBackend,
    Headers,
    HeaderTypes,
    ProxySpec,
    Request,
    Response,
    Session,
    WebSocket,
    WebSocketClosed,
    WebSocketError,
    WebSocketTimeout,
    WebSocketRetryStrategy,
    WsCloseCode,
    delete,
    exceptions,
    get,
    head,
    options,
    patch,
    post,
    put,
    request,
)

from .utils import config_warnings
from .fingerprints import Fingerprint, FingerprintManager, get_fingerprint

config_warnings(on=False)
