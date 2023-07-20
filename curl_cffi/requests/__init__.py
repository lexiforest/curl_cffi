__all__ = [
    "Session",
    "AsyncSession",
    "BrowserType",
    "request",
    "get",
    "post",
    "put",
    "delete",
    "RequestsError",
    "Cookies",
    "Headers",
    "Response",
]
from functools import partial
from io import BytesIO
from typing import Callable, Dict, Optional, Tuple, Union

from .cookies import Cookies, CookieTypes, Response
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .session import AsyncSession, BrowserType, Session

# ThreadType = Literal["eventlet", "gevent", None]


def request(
    method: str,
    url: str,
    params: Optional[dict] = None,
    data: Optional[Union[Dict[str, str], str, BytesIO, bytes]] = None,
    json: Optional[dict] = None,
    headers: Optional[HeaderTypes] = None,
    cookies: Optional[CookieTypes] = None,
    files: Optional[Dict] = None,
    auth: Optional[Tuple[str, str]] = None,
    timeout: Union[float, Tuple[float, float]] = 30,
    allow_redirects: bool = True,
    max_redirects: int = -1,
    proxies: Optional[dict] = None,
    verify: Optional[bool] = None,
    referer: Optional[str] = None,
    accept_encoding: Optional[str] = "gzip, deflate, br",
    content_callback: Optional[Callable] = None,
    impersonate: Optional[Union[str, BrowserType]] = None,
    thread: Optional[str] = None,
    default_headers: Optional[bool] = None,
) -> Response:
    """Send a http request.

    Parameters:
        method: http method for the request: GET/POST/PUT/DELETE etc.
        url: url for the requests.
        params: query string for the requests.
        data: form values or binary data to use in body, `Content-Type: application/x-www-form-urlencoded` will be added if a dict is given.
        json: json values to use in body, `Content-Type: application/json` will be added automatically.
        headers: headers to send.
        cookies: cookies to use.
        files: not implemented yet.
        auth: HTTP basic auth, a tuple of (username, password), only basic auth is supported.
        timeout: how many seconds to wait before giving up.
        allow_redirects: whether to allow redirection.
        max_redirects: max redirect counts, default unlimited(-1).
        proxies: dict of proxies to use, format: {"http": proxy_url, "https": proxy_url}.
        verify: whether to verify https certs.
        referer: shortcut for setting referer header.
        accept_encoding: shortcut for setting accept-encoding header.
        content_callback: a callback function to receive response body. `def callback(chunk: bytes):`
        impersonate: which browser version to impersonate.
        thread: work with other thread implementations. choices: eventlet, gevent.

    Returns:
        A [Response](/api/curl_cffi.requests#curl_cffi.requests.Response) object.
    """
    with Session(thread=thread) as s:
        return s.request(
            method,
            url,
            params,
            data,
            json,
            headers,
            cookies,
            files,
            auth,
            timeout,
            allow_redirects,
            max_redirects,
            proxies,
            verify,
            referer,
            accept_encoding,
            content_callback,
            impersonate,
            default_headers,
        )


head = partial(request, "HEAD")
get = partial(request, "GET")
post = partial(request, "POST")
put = partial(request, "PUT")
patch = partial(request, "PATCH")
delete = partial(request, "DELETE")
options = partial(request, "OPTIONS")
