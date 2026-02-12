from __future__ import annotations

import asyncio
import http.cookies
import os
import queue
import random
import sys
import threading
import time
import warnings
from collections.abc import AsyncGenerator, Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager, contextmanager, suppress
from dataclasses import dataclass
from datetime import timedelta
from io import BytesIO
from typing import (
    TYPE_CHECKING,
    Generic,
    Literal,
    Optional,
    TypedDict,
    TypeVar,
    Union,
    cast,
)
from urllib.parse import urlparse

from ..aio import AsyncCurl
from ..const import CurlHttpVersion, CurlInfo, CurlOpt
from ..curl import Curl, CurlError, CurlMime
from ..utils import CurlCffiWarning
from .cookies import Cookies, CookieTypes, CurlMorsel
from .exceptions import RequestException, SessionClosed, code2error
from .headers import Headers, HeaderTypes
from .impersonate import BrowserTypeLiteral, ExtraFingerprints, ExtraFpDict
from .models import STREAM_END, Response
from .utils import NOT_SET, HttpVersionLiteral, NotSetType, set_curl_options
from .websockets import (
    AsyncWebSocket,
    AsyncWebSocketContext,
    WebSocket,
    WebSocketError,
    WebSocketRetryStrategy,
)

# Added in 3.13: https://docs.python.org/3/library/typing.html#typing.TypeVar.__default__
if sys.version_info >= (3, 13):
    R = TypeVar("R", bound=Response, default=Response)
else:
    R = TypeVar("R", bound=Response)

if TYPE_CHECKING:
    from typing_extensions import Unpack

    class ProxySpec(TypedDict, total=False):
        all: str
        http: str
        https: str
        ws: str
        wss: str

    class BaseSessionParams(Generic[R], TypedDict, total=False):
        headers: Optional[HeaderTypes]
        cookies: Optional[CookieTypes]
        auth: Optional[tuple[str, str]]
        proxies: Optional[ProxySpec]
        proxy: Optional[str]
        proxy_auth: Optional[tuple[str, str]]
        base_url: Optional[str]
        params: Optional[dict]
        verify: bool
        timeout: Union[float, tuple[float, float]]
        trust_env: bool
        allow_redirects: bool
        max_redirects: int
        retry: Union[int, RetryStrategy]
        impersonate: Optional[BrowserTypeLiteral]
        ja3: Optional[str]
        akamai: Optional[str]
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]]
        default_headers: bool
        default_encoding: Union[str, Callable[[bytes], str]]
        curl_options: Optional[dict]
        curl_infos: Optional[list]
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]]
        debug: bool
        interface: Optional[str]
        cert: Optional[Union[str, tuple[str, str]]]
        response_class: Optional[type[R]]
        discard_cookies: bool
        raise_for_status: bool

    class StreamRequestParams(TypedDict, total=False):
        params: Optional[Union[dict, list, tuple]]
        data: Optional[Union[dict[str, str], list[tuple], str, BytesIO, bytes]]
        json: Optional[dict | list]
        headers: Optional[HeaderTypes]
        cookies: Optional[CookieTypes]
        files: Optional[dict]
        auth: Optional[tuple[str, str]]
        timeout: Optional[Union[float, tuple[float, float], object]]
        allow_redirects: Optional[bool]
        max_redirects: Optional[int]
        proxies: Optional[ProxySpec]
        proxy: Optional[str]
        proxy_auth: Optional[tuple[str, str]]
        verify: Optional[bool]
        referer: Optional[str]
        accept_encoding: Optional[str]
        content_callback: Optional[Callable]
        impersonate: Optional[BrowserTypeLiteral]
        ja3: Optional[str]
        akamai: Optional[str]
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]]
        default_headers: Optional[bool]
        default_encoding: Union[str, Callable[[bytes], str]]
        quote: Union[str, Literal[False]]
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]]
        interface: Optional[str]
        cert: Optional[Union[str, tuple[str, str]]]
        max_recv_speed: int
        multipart: Optional[CurlMime]
        discard_cookies: bool

    class RequestParams(StreamRequestParams, total=False):
        stream: Optional[bool]

else:

    class _Unpack:
        @staticmethod
        def __getitem__(*args, **kwargs):
            pass

    Unpack = _Unpack()

    ProxySpec = dict[str, str]
    BaseSessionParams = TypedDict
    StreamRequestParams, RequestParams = TypedDict, TypedDict

ThreadType = Literal["eventlet", "gevent"]
HttpMethod = Literal[
    "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY"
]


def _is_absolute_url(url: str) -> bool:
    """Check if the provided url is an absolute url"""
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme and parsed_url.hostname)


def _peek_queue(q: queue.Queue, default=None):
    try:
        return q.queue[0]
    except IndexError:
        return default


def _peek_aio_queue(q: asyncio.Queue, default=None):
    try:
        return q._queue[0]  # type: ignore
    except IndexError:
        return default


RetryBackoff = Literal["linear", "exponential"]


@dataclass
class RetryStrategy:
    count: int
    delay: float = 0.0
    jitter: float = 0.0
    backoff: RetryBackoff = "linear"


def _normalize_retry(retry: Optional[Union[int, RetryStrategy]]) -> RetryStrategy:
    if retry is None:
        retry = 0
    if isinstance(retry, RetryStrategy):
        strategy = retry
    elif isinstance(retry, int):
        strategy = RetryStrategy(count=retry)
    else:
        raise TypeError("retry must be an int or RetryStrategy")
    if strategy.count < 0:
        raise ValueError("retry.count must be >= 0")
    if strategy.delay < 0:
        raise ValueError("retry.delay must be >= 0")
    if strategy.jitter < 0:
        raise ValueError("retry.jitter must be >= 0")
    if strategy.backoff not in ("linear", "exponential"):
        raise ValueError("retry.backoff must be 'linear' or 'exponential'")
    return strategy


class BaseSession(Generic[R]):
    """Provide common methods for setting curl options and reading info in sessions."""

    def __init__(
        self,
        *,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[tuple[str, str]] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        base_url: Optional[str] = None,
        params: Optional[dict[str, object]] = None,
        verify: bool = True,
        timeout: Union[float, tuple[float, float]] = 30,
        trust_env: bool = True,
        allow_redirects: bool = True,
        max_redirects: int = 30,
        retry: Optional[Union[int, RetryStrategy]] = 0,
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: bool = True,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
        curl_options: Optional[dict[CurlOpt, str]] = None,
        curl_infos: Optional[list[object]] = None,
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]] = None,
        debug: bool = False,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        response_class: Optional[type[R]] = None,
        discard_cookies: bool = False,
        raise_for_status: bool = False,
    ):
        self.headers = Headers(headers)
        self._cookies = Cookies(cookies)  # guarded by @property
        self.auth = auth
        self.base_url = base_url
        self.params = params
        self.verify = verify
        self.timeout = timeout
        self.trust_env = trust_env
        self.allow_redirects = allow_redirects
        self.max_redirects = max_redirects
        self.retry = _normalize_retry(retry)
        self.impersonate = impersonate
        self.ja3 = ja3
        self.akamai = akamai
        self.extra_fp = extra_fp
        self.default_headers = default_headers
        self.default_encoding = default_encoding
        self.curl_options = curl_options or {}
        self.curl_infos = curl_infos or []
        self.http_version = http_version
        self.debug = debug
        self.interface = interface
        self.cert = cert

        if response_class is not None and issubclass(response_class, Response) is False:
            raise TypeError(
                "`response_class` must be a subclass of "
                "`curl_cffi.requests.models.Response`, "
                f"not of type `{response_class}`"
            )
        self.response_class = response_class or Response
        self.discard_cookies = discard_cookies
        self.raise_for_status = raise_for_status

        if proxy and proxies:
            raise TypeError("Cannot specify both 'proxy' and 'proxies'")
        if proxy:
            proxies = {"all": proxy}
        self.proxies: ProxySpec = proxies or {}
        self.proxy_auth = proxy_auth

        if self.base_url and not _is_absolute_url(self.base_url):
            raise ValueError("You need to provide an absolute url for 'base_url'")

        self._closed = False
        # Look for requests environment configuration
        # and be compatible with cURL.
        if self.verify is True or self.verify is None:
            self.verify = (
                os.environ.get("REQUESTS_CA_BUNDLE")
                or os.environ.get("CURL_CA_BUNDLE")
                or self.verify
            )

    def _parse_response(
        self,
        curl: Curl,
        buffer: BytesIO,
        header_buffer: BytesIO,
        default_encoding: Union[str, Callable[[bytes], str]],
        discard_cookies: bool,
    ) -> R:
        c = curl
        rsp = cast(R, self.response_class(c))
        rsp.url = cast(bytes, c.getinfo(CurlInfo.EFFECTIVE_URL)).decode()
        if buffer:
            rsp.content = buffer.getvalue()
        rsp.http_version = cast(int, c.getinfo(CurlInfo.HTTP_VERSION))
        rsp.status_code = cast(int, c.getinfo(CurlInfo.RESPONSE_CODE))
        rsp.ok = 200 <= rsp.status_code < 400
        header_lines = header_buffer.getvalue().splitlines()

        # TODO: history urls
        header_list: list[bytes] = []
        for header_line in header_lines:
            if not header_line.strip():
                continue
            if header_line.startswith(b"HTTP/"):
                # read header from last response
                rsp.reason = c.get_reason_phrase(header_line).decode()
                # empty header list for new redirected response
                header_list = []
                continue
            if header_line.startswith(b" ") or header_line.startswith(b"\t"):
                header_list[-1] += header_line
                continue
            header_list.append(header_line)
        rsp.headers = Headers(header_list)

        # Response cookies - only from Set-Cookie headers
        rsp.cookies = Cookies()
        set_cookie_headers = rsp.headers.get_list("set-cookie")
        for set_cookie in set_cookie_headers:
            try:
                cookie = http.cookies.SimpleCookie()
                cookie.load(set_cookie)  # type: ignore
                for name, morsel in cookie.items():
                    rsp.cookies.set(
                        name,
                        morsel.value,
                        domain=morsel.get("domain", ""),
                        path=morsel.get("path", "/"),
                        secure=bool(morsel.get("secure")),
                    )
            except Exception:
                continue

        # Session cookies - from full cookie store
        discard_cookies = discard_cookies or self.discard_cookies
        if not discard_cookies:
            morsels = [
                CurlMorsel.from_curl_format(c) for c in c.getinfo(CurlInfo.COOKIELIST)
            ]
            self._cookies.update_cookies_from_curl(morsels)

        rsp.primary_ip = cast(bytes, c.getinfo(CurlInfo.PRIMARY_IP)).decode()
        rsp.primary_port = cast(int, c.getinfo(CurlInfo.PRIMARY_PORT))
        rsp.local_ip = cast(bytes, c.getinfo(CurlInfo.LOCAL_IP)).decode()
        rsp.local_port = cast(int, c.getinfo(CurlInfo.LOCAL_PORT))
        rsp.default_encoding = default_encoding
        rsp.elapsed = timedelta(seconds=cast(float, c.getinfo(CurlInfo.TOTAL_TIME)))
        rsp.redirect_count = cast(int, c.getinfo(CurlInfo.REDIRECT_COUNT))
        redirect_url_bytes = cast(bytes, c.getinfo(CurlInfo.REDIRECT_URL))
        try:
            rsp.redirect_url = redirect_url_bytes.decode()
        except UnicodeDecodeError:
            rsp.redirect_url = redirect_url_bytes.decode("latin-1")

        rsp.download_size = cast(int, c.getinfo(CurlInfo.SIZE_DOWNLOAD_T))
        rsp.upload_size = cast(int, c.getinfo(CurlInfo.SIZE_UPLOAD_T))
        rsp.header_size = cast(int, c.getinfo(CurlInfo.HEADER_SIZE))
        rsp.request_size = cast(int, c.getinfo(CurlInfo.REQUEST_SIZE))
        rsp.response_size = rsp.download_size + rsp.header_size

        # custom info options
        for info in self.curl_infos:
            rsp.infos[info] = c.getinfo(info)

        return rsp

    def _check_session_closed(self):
        if self._closed:
            raise SessionClosed("Session is closed, cannot send request.")

    def _retry_delay(self, attempt: int) -> float:
        strategy = self.retry
        if strategy.backoff == "exponential":
            delay = strategy.delay * (2 ** (attempt - 1))
        else:
            delay = strategy.delay * attempt
        if strategy.jitter:
            delay += random.uniform(0.0, strategy.jitter)
        return delay

    @property
    def cookies(self) -> Cookies:
        return self._cookies

    @cookies.setter
    def cookies(self, cookies: CookieTypes) -> None:
        # This ensures that the cookies property is always converted to Cookies.
        self._cookies = Cookies(cookies)


class Session(BaseSession[R]):
    """A request session, cookies and connections will be reused. This object is
    thread-safe, but it's recommended to use a separate session for each thread."""

    def __init__(
        self,
        curl: Optional[Curl] = None,
        thread: Optional[ThreadType] = None,
        use_thread_local_curl: bool = True,
        **kwargs: Unpack[BaseSessionParams[R]],
    ) -> None:
        """
        Parameters set in the ``__init__`` method will be overridden by the same
        parameter in request method.

        Args:
            curl: curl object to use in the session. If not provided, a new one will be
                created. Also, a fresh curl object will always be created when accessed
                from another thread.
            thread: thread engine to use for working with other thread implementations.
                choices: eventlet, gevent.
            headers: headers to use in the session.
            cookies: cookies to add in the session.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is
                supported.
            proxies: dict of proxies to use, prefer to use proxy if they are the same.
                format: ``{"http": proxy_url, "https": proxy_url}``.
            proxy: proxy to use, format: "http://proxy_url".
                Cannot be used with the above parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            base_url: absolute url to use as base for relative urls.
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up.
            trust_env: use http_proxy/https_proxy and other environments, default True.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default 30, use -1 for unlimited.
            retry: number of retries or ``RetryStrategy`` for failed requests.
            impersonate: which browser version to impersonate in the session.
            ja3: ja3 string to impersonate in the session.
            akamai: akamai string to impersonate in the session.
            extra_fp: extra fingerprints options, in complement to ja3 and akamai str.
            interface: which interface use.
            default_encoding: encoding for decoding response content if charset is not
                found in headers. Defaults to "utf-8". Can be set to a callable for
                automatic detection.
            cert: a tuple of (cert, key) filenames for client cert.
            response_class: A customized subtype of ``Response`` to use.
            raise_for_status: automatically raise an HTTPError for 4xx and 5xx
                status codes.

        Notes:
            This class can be used as a context manager.

        .. code-block:: python

            from curl_cffi.requests import Session

            with Session() as s:
                r = s.get("https://example.com")
        """
        super().__init__(**kwargs)
        self._thread = thread
        self._use_thread_local_curl = use_thread_local_curl
        self._queue = None
        self._executor = None
        if use_thread_local_curl:
            self._local = threading.local()
            if curl:
                self._is_customized_curl = True
                self._local.curl = curl
            else:
                self._is_customized_curl = False
                self._local.curl = Curl(debug=self.debug)
        else:
            self._curl = curl if curl else Curl(debug=self.debug)

    @property
    def curl(self):
        if self._use_thread_local_curl:
            if self._is_customized_curl:
                warnings.warn(
                    "Creating fresh curl handle in different thread.",
                    CurlCffiWarning,
                    stacklevel=2,
                )
            if not getattr(self._local, "curl", None):
                self._local.curl = Curl(debug=self.debug)
            return self._local.curl
        else:
            return self._curl

    @property
    def executor(self):
        if self._executor is None:
            self._executor = ThreadPoolExecutor()
        return self._executor

    def __enter__(self):
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def close(self) -> None:
        """Close the session."""
        self._closed = True
        self.curl.close()

    @contextmanager
    def stream(
        self,
        method: HttpMethod,
        url: str,
        **kwargs: Unpack[StreamRequestParams],
    ) -> Generator[R, None, None]:
        """Equivalent to ``with request(..., stream=True) as r:``"""
        rsp = self.request(method=method, url=url, **kwargs, stream=True)
        try:
            yield rsp
        finally:
            rsp.close()

    def ws_connect(
        self,
        url: str,
        on_message=None,
        on_error=None,
        on_open=None,
        on_close=None,
        **kwargs,
    ) -> WebSocket:
        """Connects to a websocket url.

        Note: This method is deprecated, use WebSocket instead.

        Args:
            url: the ws url to connect.
            on_message: message callback, ``def on_message(ws, str)``
            on_error: error callback, ``def on_error(ws, error)``
            on_open: open callback, ``def on_open(ws)``
            on_close: close callback, ``def on_close(ws)``

        Other parameters are the same as ``.request``

        Returns:
            a WebSocket instance to communicate with the server.
        """
        self._check_session_closed()

        curl = self.curl.duphandle()
        self.curl.reset()

        ws: WebSocket = WebSocket(
            curl=curl,
            on_message=on_message,
            on_error=on_error,
            on_open=on_open,
            on_close=on_close,
            debug=self.debug,
        )

        # Fix session cookies being ignored
        user_cookies = cast(Cookies | None, kwargs.get("cookies"))
        if user_cookies is not None:
            merged_cookies = Cookies(self.cookies)
            merged_cookies.update(user_cookies)
            kwargs["cookies"] = merged_cookies
        else:
            kwargs["cookies"] = self.cookies

        ws.connect(url, **kwargs)
        return ws

    def upkeep(self) -> int:
        return self.curl.upkeep()

    def _request_once(
        self,
        method: HttpMethod,
        url: str,
        params: Optional[
            Union[dict[str, object], list[object], tuple[object, ...]]
        ] = None,
        data: Optional[
            Union[dict[str, str], list[tuple[object, ...]], str, BytesIO, bytes]
        ] = None,
        json: Optional[dict | list] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[dict] = None,
        auth: Optional[tuple[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float], object]] = NOT_SET,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable[..., object]] = None,
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: Optional[bool] = None,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
        quote: Union[str, Literal[False]] = "",
        http_version: CurlHttpVersion | HttpVersionLiteral | None = None,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        stream: Optional[bool] = None,
        max_recv_speed: int = 0,
        multipart: Optional[CurlMime] = None,
        discard_cookies: bool = False,
    ) -> R:
        # clone a new curl instance for streaming response
        if stream:
            c = self.curl.duphandle()
            _ = self.curl.reset()
        else:
            c = self.curl

        req, buffer, header_buffer, q, header_recved, quit_now = set_curl_options(
            c,
            method=method,
            url=url,
            params_list=[self.params, params],
            base_url=self.base_url,
            data=data,
            json=json,
            headers_list=[self.headers, headers],
            cookies_list=[self._cookies, cookies],
            files=files,
            auth=auth or self.auth,
            timeout=self.timeout if timeout is NOT_SET else timeout,
            allow_redirects=(
                self.allow_redirects if allow_redirects is None else allow_redirects
            ),
            max_redirects=(
                self.max_redirects if max_redirects is None else max_redirects
            ),
            proxies_list=[self.proxies, proxies],
            proxy=proxy,
            proxy_auth=proxy_auth or self.proxy_auth,
            verify_list=[self.verify, verify],
            referer=referer,
            accept_encoding=accept_encoding,
            content_callback=content_callback,
            impersonate=impersonate or self.impersonate,
            ja3=ja3 or self.ja3,
            akamai=akamai or self.akamai,
            extra_fp=extra_fp or self.extra_fp,
            default_headers=(
                self.default_headers if default_headers is None else default_headers
            ),
            quote=quote,
            http_version=http_version or self.http_version,
            interface=interface or self.interface,
            stream=stream,
            max_recv_speed=max_recv_speed,
            multipart=multipart,
            cert=cert or self.cert,
            curl_options=self.curl_options,
            queue_class=queue.Queue,
            event_class=threading.Event,
        )

        if stream:

            def perform():
                try:
                    c.perform()
                except CurlError as e:
                    rsp = self._parse_response(
                        c, buffer, header_buffer, default_encoding, discard_cookies
                    )
                    rsp.request = req
                    q.put_nowait(RequestException(str(e), e.code, rsp))  # type: ignore
                finally:
                    if not cast(threading.Event, header_recved).is_set():
                        cast(threading.Event, header_recved).set()
                    q.put(STREAM_END)  # type: ignore

            stream_task = self.executor.submit(perform)

            # Wait for the first chunk
            header_recved.wait()  # type: ignore
            rsp = self._parse_response(
                c, buffer, header_buffer, default_encoding, discard_cookies
            )

            # Raise the exception if something wrong happens when receiving the header.
            first_element = _peek_queue(q)  # type: ignore
            if isinstance(first_element, RequestException):
                if quit_now:
                    quit_now.set()
                stream_task.result()
                c.close()
                raise first_element

            rsp.request = req
            rsp.stream_task = stream_task
            rsp.quit_now = quit_now
            rsp.queue = q
            if self.raise_for_status:
                rsp.raise_for_status()
            return rsp
        else:
            try:
                if self._thread == "eventlet":
                    # see: https://eventlet.net/doc/threading.html
                    import eventlet.tpool

                    eventlet.tpool.execute(c.perform)  # type: ignore
                elif self._thread == "gevent":
                    # see: https://www.gevent.org/api/gevent.threadpool.html
                    import gevent

                    gevent.get_hub().threadpool.spawn(c.perform).get()  # type: ignore
                else:
                    c.perform()
            except CurlError as e:
                rsp = self._parse_response(
                    c, buffer, header_buffer, default_encoding, discard_cookies
                )
                rsp.request = req
                error = code2error(e.code, str(e))
                raise error(str(e), e.code, rsp) from e
            else:
                rsp = self._parse_response(
                    c, buffer, header_buffer, default_encoding, discard_cookies
                )
                rsp.request = req
                if self.raise_for_status:
                    rsp.raise_for_status()
                return rsp
            finally:
                c.reset()

    def request(
        self,
        method: HttpMethod,
        url: str,
        params: Optional[Union[dict, list, tuple]] = None,
        data: Optional[Union[dict[str, str], list[tuple], str, BytesIO, bytes]] = None,
        json: Optional[dict | list] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[dict] = None,
        auth: Optional[tuple[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float], object]] = NOT_SET,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable] = None,
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: Optional[bool] = None,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
        quote: Union[str, Literal[False]] = "",
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]] = None,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        stream: Optional[bool] = None,
        max_recv_speed: int = 0,
        multipart: Optional[CurlMime] = None,
        discard_cookies: bool = False,
    ):
        """Send the request, see ``requests.request`` for details on parameters."""

        self._check_session_closed()

        strategy = self.retry
        for attempt in range(strategy.count + 1):
            try:
                return self._request_once(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    cookies=cookies,
                    files=files,
                    auth=auth,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    max_redirects=max_redirects,
                    proxies=proxies,
                    proxy=proxy,
                    proxy_auth=proxy_auth,
                    verify=verify,
                    referer=referer,
                    accept_encoding=accept_encoding,
                    content_callback=content_callback,
                    impersonate=impersonate,
                    ja3=ja3,
                    akamai=akamai,
                    extra_fp=extra_fp,
                    default_headers=default_headers,
                    default_encoding=default_encoding,
                    quote=quote,
                    http_version=http_version,
                    interface=interface,
                    cert=cert,
                    stream=stream,
                    max_recv_speed=max_recv_speed,
                    multipart=multipart,
                    discard_cookies=discard_cookies,
                )
            except RequestException:
                if attempt == strategy.count:
                    raise
                delay = self._retry_delay(attempt + 1)
                if delay:
                    time.sleep(delay)

    def head(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="HEAD", url=url, **kwargs)

    def get(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="GET", url=url, **kwargs)

    def post(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="POST", url=url, **kwargs)

    def put(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="PUT", url=url, **kwargs)

    def patch(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="PATCH", url=url, **kwargs)

    def delete(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="DELETE", url=url, **kwargs)

    def options(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="OPTIONS", url=url, **kwargs)

    def trace(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="TRACE", url=url, **kwargs)

    def query(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return self.request(method="QUERY", url=url, **kwargs)


class AsyncSession(BaseSession[R]):
    """An async request session, cookies and connections will be reused."""

    def __init__(
        self,
        *,
        loop: asyncio.AbstractEventLoop | None = None,
        async_curl: AsyncCurl | None = None,
        max_clients: int = 10,
        **kwargs: Unpack[BaseSessionParams[R]],
    ) -> None:
        """
        Parameters set in the ``__init__`` method are overridden by the same parameter
        in request method.

        Parameters:
            loop: loop to use, if not provided, the running loop will be used.
            async_curl: [AsyncCurl](/api/curl_cffi#curl_cffi.AsyncCurl) object to use.
            max_clients: maxmium curl handle to use in the session,
                this will affect the concurrency ratio.
            headers: headers to use in the session.
            cookies: cookies to add in the session.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is
                supported.
            proxies: dict of proxies to use, prefer to use ``proxy`` if they are the
                same. format: ``{"http": proxy_url, "https": proxy_url}``.
            proxy: proxy to use, format: "http://proxy_url".
                Cannot be used with the above parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            base_url: absolute url to use for relative urls.
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up.
            trust_env: use http_proxy/https_proxy and other environments, default True.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default 30, use -1 for unlimited.
            retry: number of retries or ``RetryStrategy`` for failed requests.
            impersonate: which browser version to impersonate in the session.
            ja3: ja3 string to impersonate in the session.
            akamai: akamai string to impersonate in the session.
            extra_fp: extra fingerprints options, in complement to ja3 and akamai str.
            default_encoding: encoding for decoding response content if charset is not
                found in headers. Defaults to "utf-8". Can be set to a callable for
                automatic detection.
            cert: a tuple of (cert, key) filenames for client cert.
            response_class: A customized subtype of ``Response`` to use.
            raise_for_status: automatically raise an HTTPError for 4xx and 5xx
                status codes.

        Notes:
            This class can be used as a context manager, and it's recommended to use via
            ``async with``.
            However, unlike aiohttp, it is not required to use ``with``.

        .. code-block:: python

            from curl_cffi.requests import AsyncSession

            # recommended.
            async with AsyncSession() as s:
                r = await s.get("https://example.com")

            s = AsyncSession()  # it also works.
        """
        super().__init__(**kwargs)
        self._loop: asyncio.AbstractEventLoop | None = loop
        self._acurl: AsyncCurl | None = async_curl
        self.max_clients: int = max_clients
        self.init_pool()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Returns a reference to event loop."""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    @property
    def acurl(self) -> AsyncCurl:
        if self._acurl is None:
            self._acurl = AsyncCurl(loop=self.loop)
        return self._acurl

    def init_pool(self):
        self.pool: asyncio.LifoQueue[Curl | None] = asyncio.LifoQueue(self.max_clients)
        while True:
            try:
                self.pool.put_nowait(None)
            except asyncio.QueueFull:
                break

    async def pop_curl(self) -> Curl:
        curl: Curl | None = await self.pool.get()
        if curl is None:
            curl = Curl(debug=self.debug)
        return curl

    def push_curl(self, curl: Curl | None) -> None:
        with suppress(asyncio.QueueFull):
            self.pool.put_nowait(curl)

    async def __aenter__(self):  # TODO: -> Self
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()
        return None

    async def close(self) -> None:
        """Close the session."""
        await self.acurl.close()
        self._closed = True
        while True:
            try:
                curl = self.pool.get_nowait()
                if curl:
                    curl.close()
            except asyncio.QueueEmpty:
                break

    def release_curl(self, curl: Curl) -> None:
        curl.clean_handles_and_buffers()
        if not self._closed:
            self.acurl.remove_handle(curl)
            curl.reset()
            self.push_curl(curl)
        else:
            curl.close()

    @asynccontextmanager
    async def stream(
        self,
        method: HttpMethod,
        url: str,
        **kwargs: Unpack[StreamRequestParams],
    ) -> AsyncGenerator[R, None, None]:
        """Equivalent to ``async with request(..., stream=True) as r:``"""
        rsp = await self.request(method=method, url=url, **kwargs, stream=True)
        try:
            yield rsp
        finally:
            await rsp.aclose()

    def ws_connect(
        self,
        url: str,
        autoclose: bool = True,
        params: dict[str, object] | list[object] | tuple[object, ...] | None = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float | tuple[float, float] | NotSetType | None = NOT_SET,
        allow_redirects: bool | None = None,
        max_redirects: int | None = None,
        proxies: ProxySpec | None = None,
        proxy: str | None = None,
        proxy_auth: tuple[str, str] | None = None,
        verify: bool | None = None,
        referer: str | None = None,
        accept_encoding: str | None = "gzip, deflate, br",
        impersonate: BrowserTypeLiteral | None = None,
        ja3: str | None = None,
        akamai: str | None = None,
        extra_fp: ExtraFingerprints | ExtraFpDict | None = None,
        default_headers: bool | None = None,
        quote: str | Literal[False] = "",
        http_version: CurlHttpVersion | HttpVersionLiteral | None = None,
        interface: str | None = None,
        cert: str | tuple[str, str] | None = None,
        max_recv_speed: int = 0,
        recv_queue_size: int = 32,
        send_queue_size: int = 16,
        max_send_batch_size: int = 32,
        coalesce_frames: bool = False,
        ws_retry: WebSocketRetryStrategy | None = None,
        recv_time_slice: float = 0.005,
        send_time_slice: float = 0.001,
        max_message_size: int = 4 * 1024 * 1024,
        drain_on_error: bool = False,
        block_on_recv_queue_full: bool = True,
        curl_options: dict[CurlOpt, str] | None = None,
    ) -> AsyncWebSocketContext:
        """Connects to a WebSocket.

        Args:
            url: url for the requests.
            autoclose: whether to close the WebSocket after receiving a close frame.
            params: query string for the requests.
            headers: headers to send.
            cookies: cookies to use.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is
                supported.
            timeout: how many seconds to wait before giving up.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default 30, use -1 for unlimited.
            proxies: dict of proxies to use, prefer to use ``proxy`` if they are the
                same. format: ``{"http": proxy_url, "https": proxy_url}``.
            proxy: proxy to use, format: "http://user@pass:proxy_url".
                Can't be used with `proxies` parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            verify: whether to verify https certs.
            referer: shortcut for setting referer header.
            accept_encoding: shortcut for setting accept-encoding header.
            impersonate: which browser version to impersonate.
            ja3: ja3 string to impersonate.
            akamai: akamai string to impersonate.
            extra_fp: extra fingerprints options, in complement to ja3 and akamai str.
            default_headers: whether to set default browser headers.
            quote: Set characters to be quoted, i.e. percent-encoded. Default safe
                string is ``!#$%&'()*+,/:;=?@[]~``. If set to a string, the character
                will be removed from the safe string, thus quoted. If set to False, the
                url will be kept as is, without any automatic percent-encoding, you must
                encode the URL yourself.
            http_version: limiting http version, defaults to http2.
            interface: which interface to use.
            cert: a tuple of (cert, key) filenames for client cert.
            max_recv_speed: maximum receive speed, bytes per second.
            recv_queue_size: The maximum number of incoming WebSocket
                messages to buffer internally. This queue stores messages received by
                the Curl socket that are waiting to be consumed on calling ``recv()``.
            send_queue_size: The maximum number of outgoing WebSocket
                messages to buffer before applying network backpressure. When you call
                ``send()`` the message is placed in this queue and transmitted when
                the Curl socket is next available for sending.
            max_send_batch_size: The max batch size for sent frames.
            coalesce_frames: When set, multiple pending messages in the send queue
                may be merged into a single WebSocket frame for improved throughput.
                **Warning:** This breaks the one-to-one mapping of ``send()`` calls
                to frames and should only be used when the application protocol is
                designed to handle concatenated data streams. Defaults to ``False``.
            ws_retry (WebSocketRetryStrategy): Retry policy for WebSocket messages.
            recv_time_slice: The maximum duration (in seconds) to process incoming
                messages before yielding to the event loop.
                Defaults to ``0.005`` (5ms).
            send_time_slice: The maximum duration (in seconds) to process outgoing
                messages before yielding to the event loop.
                Defaults to ``0.001`` (1ms).
            max_message_size: Maximum allowed size for a complete received
                WebSocket message (default: ``4 MiB``).
            drain_on_error: If ``True``, when a connection error occurs,
            attempt to consume all the buffered received messages first,
            before raising the error. Otherwise, raise it immediately (default).
            block_on_recv_queue_full (bool, optional): If ``False``, the connection
                is failed immediately when the receive queue is full. The message that
                caused the overflow is not delivered; any messages already buffered may
                still be drained if ``drain_on_error=True``.
            curl_options: extra curl options to use.
        """

        async def _connect_coro() -> AsyncWebSocket:
            self._check_session_closed()

            curl: Curl = await self.pop_curl()
            _ = set_curl_options(
                curl=curl,
                method="GET",
                url=url,
                base_url=self.base_url,
                params_list=[self.params, params],
                headers_list=[self.headers, headers],
                cookies_list=[self.cookies, cookies],
                auth=auth or self.auth,
                timeout=self.timeout if timeout is NOT_SET else timeout,
                allow_redirects=(
                    self.allow_redirects if allow_redirects is None else allow_redirects
                ),
                max_redirects=(
                    self.max_redirects if max_redirects is None else max_redirects
                ),
                proxies_list=[self.proxies, proxies],
                proxy=proxy,
                proxy_auth=proxy_auth or self.proxy_auth,
                verify_list=[self.verify, verify],
                referer=referer,
                accept_encoding=accept_encoding,
                impersonate=impersonate or self.impersonate,
                ja3=ja3 or self.ja3,
                akamai=akamai or self.akamai,
                extra_fp=extra_fp or self.extra_fp,
                default_headers=(
                    self.default_headers if default_headers is None else default_headers
                ),
                quote=quote,
                http_version=http_version or self.http_version,
                interface=interface or self.interface,
                max_recv_speed=max_recv_speed,
                cert=cert or self.cert,
                queue_class=asyncio.Queue,
                event_class=asyncio.Event,
                curl_options=curl_options,
            )
            _ = curl.setopt(CurlOpt.TCP_NODELAY, 1)
            _ = curl.setopt(
                CurlOpt.CONNECT_ONLY,
                2,  # https://curl.se/docs/websocket.html
            )

            try:
                _ = await self.loop.run_in_executor(None, curl.perform)
            except Exception:
                curl.close()
                self.push_curl(None)
                raise

            ws: AsyncWebSocket = AsyncWebSocket(
                cast(AsyncSession[Response], self),
                curl,
                autoclose=autoclose,
                recv_queue_size=recv_queue_size,
                send_queue_size=send_queue_size,
                max_send_batch_size=max_send_batch_size,
                coalesce_frames=coalesce_frames,
                ws_retry=ws_retry,
                recv_time_slice=recv_time_slice,
                send_time_slice=send_time_slice,
                max_message_size=max_message_size,
                drain_on_error=drain_on_error,
                block_on_recv_queue_full=block_on_recv_queue_full,
                debug=self.debug,
            )

            try:
                ws._start_io_tasks()
            except WebSocketError:
                ws.terminate()
                raise

            return ws

        return AsyncWebSocketContext(_connect_coro())

    async def _request_once(
        self,
        method: HttpMethod,
        url: str,
        params: Optional[Union[dict, list, tuple]] = None,
        data: Optional[Union[dict[str, str], list[tuple], str, BytesIO, bytes]] = None,
        json: Optional[dict | list] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[dict] = None,
        auth: Optional[tuple[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float], object]] = NOT_SET,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable] = None,
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: Optional[bool] = None,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
        quote: Union[str, Literal[False]] = "",
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]] = None,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        stream: Optional[bool] = None,
        max_recv_speed: int = 0,
        multipart: Optional[CurlMime] = None,
        discard_cookies: bool = False,
    ) -> R:
        curl = await self.pop_curl()
        req, buffer, header_buffer, q, header_recved, quit_now = set_curl_options(
            curl=curl,
            method=method,
            url=url,
            params_list=[self.params, params],
            base_url=self.base_url,
            data=data,
            json=json,
            headers_list=[self.headers, headers],
            cookies_list=[self.cookies, cookies],
            files=files,
            auth=auth or self.auth,
            timeout=self.timeout if timeout is NOT_SET else timeout,
            allow_redirects=(
                self.allow_redirects if allow_redirects is None else allow_redirects
            ),
            max_redirects=(
                self.max_redirects if max_redirects is None else max_redirects
            ),
            proxies_list=[self.proxies, proxies],
            proxy=proxy,
            proxy_auth=proxy_auth or self.proxy_auth,
            verify_list=[self.verify, verify],
            referer=referer,
            accept_encoding=accept_encoding,
            content_callback=content_callback,
            impersonate=impersonate or self.impersonate,
            ja3=ja3 or self.ja3,
            akamai=akamai or self.akamai,
            extra_fp=extra_fp or self.extra_fp,
            default_headers=(
                self.default_headers if default_headers is None else default_headers
            ),
            quote=quote,
            http_version=http_version or self.http_version,
            interface=interface or self.interface,
            stream=stream,
            max_recv_speed=max_recv_speed,
            multipart=multipart,
            cert=cert or self.cert,
            curl_options=self.curl_options,
            queue_class=asyncio.Queue,
            event_class=asyncio.Event,
        )
        if stream:
            task = self.acurl.add_handle(curl)

            async def perform() -> None:
                try:
                    await task
                except CurlError as e:
                    rsp = self._parse_response(
                        curl, buffer, header_buffer, default_encoding, discard_cookies
                    )
                    rsp.request = req
                    q.put_nowait(RequestException(str(e), e.code, rsp))  # type: ignore
                finally:
                    if not cast(asyncio.Event, header_recved).is_set():
                        cast(asyncio.Event, header_recved).set()
                    await q.put(STREAM_END)  # type: ignore

            def cleanup(fut):
                self.release_curl(curl)

            stream_task = asyncio.create_task(perform())
            stream_task.add_done_callback(cleanup)

            await cast(asyncio.Event, header_recved).wait()

            # Unlike threads, coroutines does not use preemptive scheduling.
            # For asyncio, there is no need for a header_parsed event, the
            # _parse_response will execute in the foreground, no background tasks
            # running.
            rsp = self._parse_response(
                curl, buffer, header_buffer, default_encoding, discard_cookies
            )

            first_element = _peek_aio_queue(q)  # type: ignore
            if isinstance(first_element, RequestException):
                self.release_curl(curl)
                raise first_element

            rsp.request = req
            rsp.astream_task = stream_task
            rsp.quit_now = quit_now
            rsp.queue = q
            if self.raise_for_status:
                rsp.raise_for_status()
            return rsp
        else:
            try:
                task = self.acurl.add_handle(curl)
                await task
            except CurlError as e:
                rsp = self._parse_response(
                    curl, buffer, header_buffer, default_encoding, discard_cookies
                )
                rsp.request = req
                error = code2error(e.code, str(e))
                raise error(str(e), e.code, rsp) from e
            else:
                rsp = self._parse_response(
                    curl, buffer, header_buffer, default_encoding, discard_cookies
                )
                rsp.request = req
                if self.raise_for_status:
                    rsp.raise_for_status()
                return rsp
            finally:
                self.release_curl(curl)

    async def request(
        self,
        method: HttpMethod,
        url: str,
        params: Optional[Union[dict, list, tuple]] = None,
        data: Optional[Union[dict[str, str], list[tuple], str, BytesIO, bytes]] = None,
        json: Optional[dict | list] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[dict] = None,
        auth: Optional[tuple[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float], object]] = NOT_SET,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable] = None,
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: Optional[bool] = None,
        default_encoding: Union[str, Callable[[bytes], str]] = "utf-8",
        quote: Union[str, Literal[False]] = "",
        http_version: Optional[Union[CurlHttpVersion, HttpVersionLiteral]] = None,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        stream: Optional[bool] = None,
        max_recv_speed: int = 0,
        multipart: Optional[CurlMime] = None,
        discard_cookies: bool = False,
    ) -> R:
        """Send the request, see ``curl_cffi.requests.request`` for details on args."""

        self._check_session_closed()

        strategy = self.retry
        for attempt in range(strategy.count + 1):
            try:
                return await self._request_once(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json=json,
                    headers=headers,
                    cookies=cookies,
                    files=files,
                    auth=auth,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    max_redirects=max_redirects,
                    proxies=proxies,
                    proxy=proxy,
                    proxy_auth=proxy_auth,
                    verify=verify,
                    referer=referer,
                    accept_encoding=accept_encoding,
                    content_callback=content_callback,
                    impersonate=impersonate,
                    ja3=ja3,
                    akamai=akamai,
                    extra_fp=extra_fp,
                    default_headers=default_headers,
                    default_encoding=default_encoding,
                    quote=quote,
                    http_version=http_version,
                    interface=interface,
                    cert=cert,
                    stream=stream,
                    max_recv_speed=max_recv_speed,
                    multipart=multipart,
                    discard_cookies=discard_cookies,
                )
            except RequestException:
                if attempt == strategy.count:
                    raise
                delay = self._retry_delay(attempt + 1)
                if delay:
                    await asyncio.sleep(delay)

    async def head(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="HEAD", url=url, **kwargs)

    async def get(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="GET", url=url, **kwargs)

    async def post(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="POST", url=url, **kwargs)

    async def put(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="PUT", url=url, **kwargs)

    async def patch(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="PATCH", url=url, **kwargs)

    async def delete(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="DELETE", url=url, **kwargs)

    async def options(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="OPTIONS", url=url, **kwargs)

    async def trace(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="TRACE", url=url, **kwargs)

    async def query(self, url: str, **kwargs: Unpack[RequestParams]) -> R:
        return await self.request(method="QUERY", url=url, **kwargs)
