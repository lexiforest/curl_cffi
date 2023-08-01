__all__ = ["Curl", "CurlInfo", "CurlOpt", "CurlMOpt", "CurlError", "AsyncCurl"]

# This line includes _wrapper.so into the wheel
from ._wrapper import ffi, lib  # type: ignore

from .const import CurlInfo, CurlMOpt, CurlOpt
from .curl import Curl, CurlError
from .aio import AsyncCurl

CURL_HTTP_VERSION_1_0 = 1  # please use HTTP 1.0 in the request */
CURL_HTTP_VERSION_1_1 = 2  # please use HTTP 1.1 in the request */
CURL_HTTP_VERSION_2_0 = 3  # please use HTTP 2 in the request */
CURL_HTTP_VERSION_2TLS = 4  # use version 2 for HTTPS, version 1.1 for HTTP */
CURL_HTTP_VERSION_2_PRIOR_KNOWLEDGE = 5  # please use HTTP 2 without HTTP/1.1 Upgrade */
CURL_HTTP_VERSION_3 = 30  # Makes use of explicit HTTP/3 without fallback.
