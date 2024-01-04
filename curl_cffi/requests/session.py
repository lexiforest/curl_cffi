import asyncio
from contextlib import contextmanager, asynccontextmanager
import re
import threading
import warnings
import queue
from functools import partialmethod
from io import BytesIO
from typing import Callable, Dict, Optional, Tuple, Union, cast, TYPE_CHECKING
from concurrent.futures import ThreadPoolExecutor

from .. import AsyncCurl, Curl, CurlError, CurlInfo, CurlOpt, CurlHttpVersion
from .cookies import Cookies, CookieTypes, CurlMorsel
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .models import BrowserType, Response
from .utils import _set_curl_options, _update_url_params, not_set
from .websockets import AsyncWebSocket

try:
    import gevent
except ImportError:
    pass

try:
    import eventlet.tpool
except ImportError:
    pass

if TYPE_CHECKING:
    from typing_extensions import TypedDict

    class ProxySpec(TypedDict, total=False):
        all: str
        http: str
        https: str
        ws: str
        wss: str

else:
    ProxySpec = Dict[str, str]


class BrowserSpec:
    """A more structured way of selecting browsers"""

    # TODO


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


class BaseSession:
    """Provide common methods for setting curl options and reading info in sessions."""

    def __init__(
        self,
        *,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[Tuple[str, str]] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        params: Optional[dict] = None,
        verify: Union[bool, str] = True,
        timeout: Union[float, Tuple[float, float]] = 30,
        trust_env: bool = True,
        allow_redirects: bool = True,
        max_redirects: int = -1,
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: bool = True,
        curl_options: Optional[dict] = None,
        curl_infos: Optional[list] = None,
        http_version: Optional[CurlHttpVersion] = None,
        debug: bool = False,
        interface: Optional[str] = None,
    ):
        self.headers = Headers(headers)
        self.cookies = Cookies(cookies)
        self.auth = auth
        self.params = params
        self.verify = verify
        self.timeout = timeout
        self.trust_env = trust_env
        self.allow_redirects = allow_redirects
        self.max_redirects = max_redirects
        self.impersonate = impersonate
        self.default_headers = default_headers
        self.curl_options = curl_options or {}
        self.curl_infos = curl_infos or []
        self.http_version = http_version
        self.debug = debug
        self.interface = interface

        if proxy and proxies:
            raise TypeError("Cannot specify both 'proxy' and 'proxies'")
        if proxy:
            proxies = {"all": proxy}
        self.proxies: ProxySpec = proxies or {}
        self.proxy_auth = proxy_auth

    def _merge_curl_options(
        self,
        curl,
        method: str,
        url: str,
        *,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float], object]] = not_set,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        verify: Optional[Union[bool, str]] = None,
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: Optional[bool] = None,
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        **kwargs,
    ):
        """Merge curl options from session and request."""
        if self.params:
            url = _update_url_params(url, self.params)

        _headers = Headers(self.headers)
        _headers.update(headers)

        if proxy and proxies:
            raise TypeError("Cannot specify both 'proxy' and 'proxies'")
        if proxy:
            proxies = {"all": proxy}
        if proxies is None:
            proxies = self.proxies

        return _set_curl_options(
            curl,
            method,
            url,
            headers=_headers,
            session_cookies=self.cookies,
            cookies=cookies,
            auth=auth or self.auth,
            timeout=self.timeout if timeout is not_set else timeout,
            allow_redirects=self.allow_redirects if allow_redirects is None else allow_redirects,
            max_redirects=self.max_redirects if max_redirects is None else max_redirects,
            proxies=proxies,
            proxy_auth=proxy_auth or self.proxy_auth,
            session_verify=self.verify,  # Not possible to merge verify parameter
            verify=verify,
            impersonate=impersonate or self.impersonate,
            default_headers=self.default_headers if default_headers is None else default_headers,
            http_version=http_version or self.http_version,
            interface=interface or self.interface,
            curl_options=self.curl_options,
            **kwargs,
        )

    def _parse_response(self, curl, buffer, header_buffer):
        c = curl
        rsp = Response(c)
        rsp.url = cast(bytes, c.getinfo(CurlInfo.EFFECTIVE_URL)).decode()
        if buffer:
            rsp.content = buffer.getvalue()  # type: ignore
        rsp.http_version = cast(int, c.getinfo(CurlInfo.HTTP_VERSION))
        rsp.status_code = cast(int, c.getinfo(CurlInfo.RESPONSE_CODE))
        rsp.ok = 200 <= rsp.status_code < 400
        header_lines = header_buffer.getvalue().splitlines()

        # TODO history urls
        header_list = []
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
        # print("Set-cookie", rsp.headers["set-cookie"])
        morsels = [CurlMorsel.from_curl_format(l) for l in c.getinfo(CurlInfo.COOKIELIST)]
        # for l in c.getinfo(CurlInfo.COOKIELIST):
        #     print("Curl Cookies", l.decode())

        self.cookies.update_cookies_from_curl(morsels)
        rsp.cookies = self.cookies
        # print("Cookies after extraction", self.cookies)

        content_type = rsp.headers.get("Content-Type", default="")
        m = re.search(r"charset=([\w-]+)", content_type)
        charset = m.group(1) if m else "utf-8"

        rsp.charset = charset
        rsp.encoding = charset  # TODO use chardet

        rsp.elapsed = cast(float, c.getinfo(CurlInfo.TOTAL_TIME))
        rsp.redirect_count = cast(int, c.getinfo(CurlInfo.REDIRECT_COUNT))
        rsp.redirect_url = cast(bytes, c.getinfo(CurlInfo.REDIRECT_URL)).decode()

        for info in self.curl_infos:
            rsp.infos[info] = c.getinfo(info)

        return rsp


# ThreadType = Literal["eventlet", "gevent", None]


class Session(BaseSession):
    """A request session, cookies and connections will be reused. This object is thread-safe,
    but it's recommended to use a seperate session for each thread."""

    def __init__(
        self,
        curl: Optional[Curl] = None,
        thread: Optional[str] = None,
        use_thread_local_curl: bool = True,
        **kwargs,
    ):
        """
        Parameters set in the init method will be override by the same parameter in request method.

        Parameters:
            curl: curl object to use in the session. If not provided, a new one will be
                created. Also, a fresh curl object will always be created when accessed
                from another thread.
            thread: thread engine to use for working with other thread implementations.
                choices: eventlet, gevent., possible values: eventlet, gevent.
            headers: headers to use in the session.
            cookies: cookies to add in the session.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is supported.
            proxies: dict of proxies to use, format: {"http": proxy_url, "https": proxy_url}.
            proxy: proxy to use, format: "http://proxy_url". Cannot be used with the above parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up. In stream mode, only connect_timeout will be set.
            trust_env: use http_proxy/https_proxy and other environments, default True.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default unlimited(-1).
            impersonate: which browser version to impersonate in the session.
            interface: which interface use in request to server.

        Notes:
            This class can be used as a context manager.
            ```
            from curl_cffi.requests import Session

            with Session() as s:
                r = s.get("https://example.com")
            ```
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
                warnings.warn("Creating fresh curl handle in different thread.")
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

    def __exit__(self, *args):
        self.close()

    def close(self):
        """Close the session."""
        self.curl.close()

    @contextmanager
    def stream(self, *args, **kwargs):
        rsp = self.request(*args, **kwargs, stream=True)
        try:
            yield rsp
        finally:
            rsp.close()

    def request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[Union[Dict[str, str], str, BytesIO, bytes]] = None,
        json: Optional[dict] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[Dict] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        verify: Optional[Union[bool, str]] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable] = None,
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: Optional[bool] = None,
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        stream: bool = False,
        max_recv_speed: int = 0,
    ) -> Response:
        """Send the request, see [curl_cffi.requests.request](/api/curl_cffi.requests/#curl_cffi.requests.request) for details on parameters."""

        # clone a new curl instance for streaming response
        if stream:
            c = self.curl.duphandle()
            self.curl.reset()
        else:
            c = self.curl

        req, buffer, header_buffer, q, header_recved, quit_now = self._merge_curl_options(
            c,
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
            default_headers=default_headers,
            http_version=http_version,
            interface=interface,
            stream=stream,
            max_recv_speed=max_recv_speed,
            queue_class=queue.Queue,
            event_class=threading.Event,
        )

        if stream:
            header_parsed = threading.Event()

            def perform():
                try:
                    c.perform()
                except CurlError as e:
                    rsp = self._parse_response(c, buffer, header_buffer)
                    rsp.request = req
                    q.put_nowait(RequestsError(str(e), e.code, rsp))  # type: ignore
                finally:
                    if not header_recved.is_set():  # type: ignore
                        header_recved.set()  # type: ignore
                    # None acts as a sentinel
                    q.put(None)  # type: ignore

            def cleanup(fut):
                header_parsed.wait()
                c.reset()

            stream_task = self.executor.submit(perform)
            stream_task.add_done_callback(cleanup)

            # Wait for the first chunk
            header_recved.wait()  # type: ignore
            rsp = self._parse_response(c, buffer, header_buffer)
            header_parsed.set()

            # Raise the exception if something wrong happens when receiving the header.
            first_element = _peek_queue(q)  # type: ignore
            if isinstance(first_element, RequestsError):
                c.reset()
                raise first_element

            rsp.request = req
            rsp.stream_task = stream_task  # type: ignore
            rsp.quit_now = quit_now  # type: ignore
            rsp.queue = q
            return rsp
        else:
            try:
                if self._thread == "eventlet":
                    # see: https://eventlet.net/doc/threading.html
                    eventlet.tpool.execute(c.perform)
                elif self._thread == "gevent":
                    # see: https://www.gevent.org/api/gevent.threadpool.html
                    gevent.get_hub().threadpool.spawn(c.perform).get()
                else:
                    c.perform()
            except CurlError as e:
                rsp = self._parse_response(c, buffer, header_buffer)
                rsp.request = req
                raise RequestsError(str(e), e.code, rsp) from e
            else:
                rsp = self._parse_response(c, buffer, header_buffer)
                rsp.request = req
                return rsp
            finally:
                c.reset()

    head = partialmethod(request, "HEAD")
    get = partialmethod(request, "GET")
    post = partialmethod(request, "POST")
    put = partialmethod(request, "PUT")
    patch = partialmethod(request, "PATCH")
    delete = partialmethod(request, "DELETE")
    options = partialmethod(request, "OPTIONS")


class AsyncSession(BaseSession):
    """An async request session, cookies and connections will be reused."""

    def __init__(
        self,
        *,
        loop=None,
        async_curl: Optional[AsyncCurl] = None,
        max_clients: int = 10,
        **kwargs,
    ):
        """
        Parameters set in the init method will be override by the same parameter in request method.

        Parameters:
            loop: loop to use, if not provided, the running loop will be used.
            async_curl: [AsyncCurl](/api/curl_cffi#curl_cffi.AsyncCurl) object to use.
            max_clients: maxmium curl handle to use in the session, this will affect the concurrency ratio.
            headers: headers to use in the session.
            cookies: cookies to add in the session.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is supported.
            proxies: dict of proxies to use, format: {"http": proxy_url, "https": proxy_url}.
            proxy: proxy to use, format: "http://proxy_url". Cannot be used with the above parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up.
            trust_env: use http_proxy/https_proxy and other environments, default True.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default unlimited(-1).
            impersonate: which browser version to impersonate in the session.

        Notes:
            This class can be used as a context manager, and it's recommended to use via `async with`.
            ```
            from curl_cffi.requests import AsyncSession

            async with AsyncSession() as s:
                r = await s.get("https://example.com")
            ```
        """
        super().__init__(**kwargs)
        self._loop = loop
        self._acurl = async_curl
        self.max_clients = max_clients
        self._closed = False
        self.init_pool()

    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    @property
    def acurl(self):
        if self._acurl is None:
            self._acurl = AsyncCurl(loop=self.loop)
        return self._acurl

    def init_pool(self):
        self.pool = asyncio.LifoQueue(self.max_clients)
        while True:
            try:
                self.pool.put_nowait(None)
            except asyncio.QueueFull:
                break

    async def pop_curl(self):
        curl = await self.pool.get()
        if curl is None:
            curl = Curl(debug=self.debug)
        return curl

    def push_curl(self, curl):
        try:
            self.pool.put_nowait(curl)
        except asyncio.QueueFull:
            pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        self.close()
        return None

    def close(self):
        """Close the session."""
        self.acurl.close()
        self._closed = True
        while True:
            try:
                curl = self.pool.get_nowait()
                if curl:
                    curl.close()
            except asyncio.QueueEmpty:
                break

    def release_curl(self, curl):
        curl.clean_after_perform()
        if not self._closed:
            self.acurl.remove_handle(curl)
            curl.reset()
            self.push_curl(curl)
        else:
            curl.close()

    @asynccontextmanager
    async def stream(self, *args, **kwargs):
        rsp = await self.request(*args, **kwargs, stream=True)
        try:
            yield rsp
        finally:
            await rsp.aclose()

    async def ws_connect(
        self,
        url,
        *,
        autoclose: bool = True,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        verify: Optional[Union[bool, str]] = True,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: Optional[bool] = None,
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        max_recv_speed: int = 0,
    ):
        """Connect to the WebSocket.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html

        Parameters:
            url: url for the requests.
            autoclose: whether to close the WebSocket after receiving a close frame.
            headers: headers to send.
            cookies: cookies to use.
            auth: HTTP basic auth, a tuple of (username, password), only basic auth is supported.
            timeout: how many seconds to wait before giving up.
            allow_redirects: whether to allow redirection.
            max_redirects: max redirect counts, default unlimited(-1).
            proxies: dict of proxies to use, format: {"http": proxy_url, "https": proxy_url}.
            proxy: proxy to use, format: "http://proxy_url". Cannot be used with the above parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            verify: whether to verify https certs.
            referer: shortcut for setting referer header.
            accept_encoding: shortcut for setting accept-encoding header.
            impersonate: which browser version to impersonate.
            default_headers: whether to set default browser headers.
            curl_options: extra curl options to use.
            http_version: limiting http version, http2 will be tries by default.
            interface: which interface use in request to server.
            max_recv_speed: max receiving speed in bytes per second.
        """
        curl = await self.pop_curl()
        self._merge_curl_options(
            curl,
            "GET",
            url,
            headers=headers,
            cookies=cookies,
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
            impersonate=impersonate,
            default_headers=default_headers,
            http_version=http_version,
            interface=interface,
            max_recv_speed=max_recv_speed,
        )
        curl.setopt(CurlOpt.CONNECT_ONLY, 2)  # https://curl.se/docs/websocket.html
        await self.loop.run_in_executor(None, curl.perform)
        return AsyncWebSocket(curl, autoclose=autoclose)

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[Union[Dict[str, str], str, BytesIO, bytes]] = None,
        json: Optional[dict] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[Dict] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        allow_redirects: Optional[bool] = None,
        max_redirects: Optional[int] = None,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        content_callback: Optional[Callable] = None,
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: Optional[bool] = None,
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        stream: bool = False,
        max_recv_speed: int = 0,
    ):
        """Send the request, see [curl_cffi.requests.request](/api/curl_cffi.requests/#curl_cffi.requests.request) for details on parameters."""
        curl = await self.pop_curl()
        req, buffer, header_buffer, q, header_recved, quit_now = self._merge_curl_options(
            curl=curl,
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
            default_headers=default_headers,
            http_version=http_version,
            interface=interface,
            stream=stream,
            max_recv_speed=max_recv_speed,
            queue_class=asyncio.Queue,
            event_class=asyncio.Event,
        )
        if stream:
            task = self.acurl.add_handle(curl)

            async def perform():
                try:
                    await task
                except CurlError as e:
                    rsp = self._parse_response(curl, buffer, header_buffer)
                    rsp.request = req
                    q.put_nowait(RequestsError(str(e), e.code, rsp))  # type: ignore
                finally:
                    if not header_recved.is_set():  # type: ignore
                        header_recved.set()  # type: ignore
                    # None acts as a sentinel
                    await q.put(None)  # type: ignore

            def cleanup(fut):
                self.release_curl(curl)

            stream_task = asyncio.create_task(perform())
            stream_task.add_done_callback(cleanup)

            await header_recved.wait()  # type: ignore

            # Unlike threads, coroutines does not use preemptive scheduling.
            # For asyncio, there is no need for a header_parsed event, the
            # _parse_response will execute in the foreground, no background tasks running.
            rsp = self._parse_response(curl, buffer, header_buffer)

            first_element = _peek_aio_queue(q)  # type: ignore
            if isinstance(first_element, RequestsError):
                self.release_curl(curl)
                raise first_element

            rsp.request = req
            rsp.stream_task = stream_task  # type: ignore
            rsp.quit_now = quit_now
            rsp.queue = q
            return rsp
        else:
            try:
                # curl.debug()
                task = self.acurl.add_handle(curl)
                await task
                # print(curl.getinfo(CurlInfo.CAINFO))
            except CurlError as e:
                rsp = self._parse_response(curl, buffer, header_buffer)
                rsp.request = req
                raise RequestsError(str(e), e.code, rsp) from e
            else:
                rsp = self._parse_response(curl, buffer, header_buffer)
                rsp.request = req
                return rsp
            finally:
                self.release_curl(curl)

    head = partialmethod(request, "HEAD")
    get = partialmethod(request, "GET")
    post = partialmethod(request, "POST")
    put = partialmethod(request, "PUT")
    patch = partialmethod(request, "PATCH")
    delete = partialmethod(request, "DELETE")
    options = partialmethod(request, "OPTIONS")
