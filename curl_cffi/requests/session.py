import asyncio
from contextlib import contextmanager, asynccontextmanager
import sys
import re
import threading
import warnings
import queue
from enum import Enum
from functools import partialmethod
from io import BytesIO
from json import dumps
from typing import Callable, Dict, List, Any, Optional, Tuple, Union, cast
from urllib.parse import ParseResult, parse_qsl, unquote, urlencode, urlparse
from concurrent.futures import ThreadPoolExecutor


from .. import AsyncCurl, Curl, CurlError, CurlInfo, CurlOpt, CurlHttpVersion
from ..curl import CURL_WRITEFUNC_ERROR
from .cookies import Cookies, CookieTypes, CurlMorsel
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .models import Request, Response

try:
    import gevent
except ImportError:
    pass

try:
    import eventlet.tpool
except ImportError:
    pass


WINDOWS_WARN = """
WindowsProactorEventLoopPolicy is not supported, you can use the selector loop by:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
"""


class BrowserType(str, Enum):
    edge99 = "edge99"
    edge101 = "edge101"
    chrome99 = "chrome99"
    chrome100 = "chrome100"
    chrome101 = "chrome101"
    chrome104 = "chrome104"
    chrome107 = "chrome107"
    chrome110 = "chrome110"
    chrome99_android = "chrome99_android"
    safari15_3 = "safari15_3"
    safari15_5 = "safari15_5"

    @classmethod
    def has(cls, item):
        return item in cls.__members__


def _update_url_params(url: str, params: Dict) -> str:
    """Add GET params to provided URL being aware of existing.

    Parameters:
        url: string of target URL
        params: dict containing requested params to be added

    Returns:
        string with updated URL

    >> url = 'http://stackoverflow.com/test?answers=true'
    >> new_params = {'answers': False, 'data': ['some','values']}
    >> _update_url_params(url, new_params)
    'http://stackoverflow.com/test?data=some&data=values&answers=false'
    """
    # Unquoting URL first so we don't loose existing args
    url = unquote(url)
    # Extracting url info
    parsed_url = urlparse(url)
    # Extracting URL arguments from parsed URL
    get_args = parsed_url.query
    # Converting URL arguments to dict
    parsed_get_args = dict(parse_qsl(get_args))
    # Merging URL arguments dict with new params
    parsed_get_args.update(params)

    # Bool and Dict values should be converted to json-friendly values
    # you may throw this part away if you don't like it :)
    parsed_get_args.update(
        {k: dumps(v) for k, v in parsed_get_args.items() if isinstance(v, (bool, dict))}
    )

    # Converting URL argument to proper query string
    encoded_get_args = urlencode(parsed_get_args, doseq=True)
    # Creating new parsed result object based on provided with new
    # URL arguments. Same thing happens inside of urlparse.
    new_url = ParseResult(
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        encoded_get_args,
        parsed_url.fragment,
    ).geturl()

    return new_url


def _update_header_line(header_lines: List[str], key: str, value: str):
    """Update header line list by key value pair."""
    for idx, line in enumerate(header_lines):
        if line.lower().startswith(key.lower() + ":"):
            header_lines[idx] = f"{key}: {value}"
            break
    else:  # if not break
        header_lines.append(f"{key}: {value}")


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


not_set = object()


class BaseSession:
    """Provide common methods for setting curl options and reading info in sessions."""

    __attrs__ = [
        "headers",
        "cookies",
        "auth",
        "proxies",
        "params",
        "verify",
        "timeout",
        "cert",
        "trust_env",  # TODO
        "max_redirects",
        "impersonate",
    ]

    def __init__(
        self,
        *,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[Tuple[str, str]] = None,
        proxies: Optional[dict] = None,
        params: Optional[dict] = None,
        verify: bool = True,
        timeout: Union[float, Tuple[float, float]] = 30,
        trust_env: bool = True,
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
        self.proxies = proxies or {}
        self.params = params
        self.verify = verify
        self.timeout = timeout
        self.trust_env = trust_env
        self.max_redirects = max_redirects
        self.impersonate = impersonate
        self.default_headers = default_headers
        self.curl_options = curl_options or {}
        self.curl_infos = curl_infos or []
        self.http_version = http_version
        self.debug = debug
        self.interface = interface

    def _set_curl_options(
        self,
        curl,
        method: str,
        url: str,
        params: Optional[dict] = None,
        data: Optional[Union[Dict[str, str], str, BytesIO, bytes]] = None,
        json: Optional[dict] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        files: Optional[Dict] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float], object]] = not_set,
        allow_redirects: bool = True,
        max_redirects: Optional[int] = None,
        proxies: Optional[dict] = None,
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
        queue_class: Any = None,
        event_class: Any = None,
    ):
        c = curl

        # method
        if method == "POST":
            c.setopt(CurlOpt.POST, 1)
        elif method != "GET":
            c.setopt(CurlOpt.CUSTOMREQUEST, method.encode())

        # url
        if self.params:
            url = _update_url_params(url, self.params)
        if params:
            url = _update_url_params(url, params)
        c.setopt(CurlOpt.URL, url.encode())

        # data/body/json
        if isinstance(data, dict):
            body = urlencode(data).encode()
        elif isinstance(data, str):
            body = data.encode()
        elif isinstance(data, BytesIO):
            body = data.read()
        elif isinstance(data, bytes):
            body = data
        elif data is None:
            body = b""
        else:
            raise TypeError("data must be dict, str, BytesIO or bytes")
        if json is not None:
            body = dumps(json, separators=(",", ":")).encode()

        # Tell libcurl to be aware of bodies and related headers when,
        # 1. POST/PUT/PATCH, even if the body is empty, it's up to curl to decide what to do;
        # 2. GET/DELETE with body, although it's against the RFC, some applications. e.g. Elasticsearch, use this.
        if body or method in ("POST", "PUT", "PATCH"):
            c.setopt(CurlOpt.POSTFIELDS, body)
            # necessary if body contains '\0'
            c.setopt(CurlOpt.POSTFIELDSIZE, len(body))

        # headers
        h = Headers(self.headers)
        h.update(headers)

        # remove Host header if it's unnecessary, otherwise curl maybe confused.
        # Host header will be automatically add by curl if it's not present.
        # https://github.com/yifeikong/curl_cffi/issues/119
        host_header = h.get("Host")
        if host_header is not None:
            u = urlparse(url)
            if host_header == u.netloc or host_header == u.hostname:
                try:
                    del h["Host"]
                except KeyError:
                    pass

        header_lines = []
        for k, v in h.multi_items():
            header_lines.append(f"{k}: {v}")
        if json is not None:
            _update_header_line(header_lines, "Content-Type", "application/json")
        if isinstance(data, dict) and method != "POST":
            _update_header_line(
                header_lines, "Content-Type", "application/x-www-form-urlencoded"
            )
        # print("header lines", header_lines)
        c.setopt(CurlOpt.HTTPHEADER, [h.encode() for h in header_lines])

        req = Request(url, h, method)

        # cookies
        c.setopt(CurlOpt.COOKIEFILE, b"")  # always enable the curl cookie engine first
        c.setopt(CurlOpt.COOKIELIST, "ALL")  # remove all the old cookies first.

        for morsel in self.cookies.get_cookies_for_curl(req):
            # print("Setting", morsel.to_curl_format())
            curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())
        if cookies:
            temp_cookies = Cookies(cookies)
            for morsel in temp_cookies.get_cookies_for_curl(req):
                curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())

        # files
        if files:
            raise NotImplementedError("Files has not been implemented.")

        # auth
        if self.auth or auth:
            if self.auth:
                username, password = self.auth
            if auth:
                username, password = auth
            c.setopt(CurlOpt.USERNAME, username.encode())  # type: ignore
            c.setopt(CurlOpt.PASSWORD, password.encode())  # type: ignore

        # timeout
        if timeout is not_set:
            timeout = self.timeout
        if timeout is None:
            timeout = 0  # indefinitely

        if isinstance(timeout, tuple):
            connect_timeout, read_timeout = timeout
            all_timeout = connect_timeout + read_timeout
            c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(connect_timeout * 1000))
            if not stream:
                c.setopt(CurlOpt.TIMEOUT_MS, int(all_timeout * 1000))
        else:
            if not stream:
                c.setopt(CurlOpt.TIMEOUT_MS, int(timeout * 1000))  # type: ignore
            else:
                c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(timeout * 1000))  # type: ignore

        # allow_redirects
        c.setopt(CurlOpt.FOLLOWLOCATION, int(allow_redirects))

        # max_redirects
        c.setopt(CurlOpt.MAXREDIRS, max_redirects or self.max_redirects)

        # proxies
        if self.proxies:
            proxies = {**self.proxies, **(proxies or {})}
        if proxies:
            if url.startswith("http://"):
                if proxies["http"] is not None:
                    c.setopt(CurlOpt.PROXY, proxies["http"])
            elif url.startswith("https://"):
                if proxies["https"] is not None:
                    if proxies["https"].startswith("https://"):
                        raise RequestsError(
                            "You are using http proxy WRONG, the prefix should be 'http://' not 'https://',"
                            "see: https://github.com/yifeikong/curl_cffi/issues/6"
                        )
                    c.setopt(CurlOpt.PROXY, proxies["https"])
                    # for http proxy, need to tell curl to enable tunneling
                    if not proxies["https"].startswith("socks"):
                        c.setopt(CurlOpt.HTTPPROXYTUNNEL, 1)

        # verify
        if verify is False or not self.verify and verify is None:
            c.setopt(CurlOpt.SSL_VERIFYPEER, 0)
            c.setopt(CurlOpt.SSL_VERIFYHOST, 0)

        # cert for this single request
        if isinstance(verify, str):
            c.setopt(CurlOpt.CAINFO, verify)

        # cert for the session
        if verify in (None, True) and isinstance(self.verify, str):
            c.setopt(CurlOpt.CAINFO, self.verify)

        # referer
        if referer:
            c.setopt(CurlOpt.REFERER, referer.encode())

        # accept_encoding
        if accept_encoding is not None:
            c.setopt(CurlOpt.ACCEPT_ENCODING, accept_encoding.encode())

        # impersonate
        impersonate = impersonate or self.impersonate
        default_headers = (
            self.default_headers if default_headers is None else default_headers
        )
        if impersonate:
            if not BrowserType.has(impersonate):
                raise RequestsError(f"impersonate {impersonate} is not supported")
            c.impersonate(impersonate, default_headers=default_headers)

        # http_version, after impersonate, which will change this to http2
        http_version = http_version or self.http_version
        if http_version:
            c.setopt(CurlOpt.HTTP_VERSION, http_version)

        # set extra curl options, must come after impersonate, because it will alter some options
        for k, v in self.curl_options.items():
            c.setopt(k, v)

        buffer = None
        q = None
        header_recved = None
        quit_now = None
        if stream:
            q = queue_class()  # type: ignore
            header_recved = event_class()
            quit_now = event_class()

            def qput(chunk):
                if not header_recved.is_set():
                    header_recved.set()
                if quit_now.is_set():
                    return CURL_WRITEFUNC_ERROR
                q.put_nowait(chunk)

            c.setopt(CurlOpt.WRITEFUNCTION, qput)  # type: ignore
        elif content_callback is not None:
            c.setopt(CurlOpt.WRITEFUNCTION, content_callback)
        else:
            buffer = BytesIO()
            c.setopt(CurlOpt.WRITEDATA, buffer)
        header_buffer = BytesIO()
        c.setopt(CurlOpt.HEADERDATA, header_buffer)

        if method == "HEAD":
            c.setopt(CurlOpt.NOBODY, 1)

        # interface
        interface = interface or self.interface
        if interface:
            c.setopt(CurlOpt.INTERFACE, interface.encode())

        # max_recv_speed
        # do not check, since 0 is a valid value to disable it
        c.setopt(CurlOpt.MAX_RECV_SPEED_LARGE, max_recv_speed)

        return req, buffer, header_buffer, q, header_recved, quit_now

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
        morsels = [
            CurlMorsel.from_curl_format(l) for l in c.getinfo(CurlInfo.COOKIELIST)
        ]
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
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up. In stream mode, only connect_timeout will be set.
            trust_env: use http_proxy/https_proxy and other environments, default True.
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
        allow_redirects: bool = True,
        max_redirects: Optional[int] = None,
        proxies: Optional[dict] = None,
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
    ) -> Response:
        """Send the request, see [curl_cffi.requests.request](/api/curl_cffi.requests/#curl_cffi.requests.request) for details on parameters."""

        # clone a new curl instance for streaming response
        if stream:
            c = self.curl.duphandle()
            self.curl.reset()
        else:
            c = self.curl

        req, buffer, header_buffer, q, header_recved, quit_now = self._set_curl_options(
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
            params: query string for the session.
            verify: whether to verify https certs.
            timeout: how many seconds to wait before giving up.
            trust_env: use http_proxy/https_proxy and other environments, default True.
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
        self.loop = loop
        self._acurl = async_curl
        self.max_clients = max_clients
        self._closed = False
        self.init_pool()
        if sys.version_info >= (3, 8) and sys.platform.lower().startswith("win"):
            if isinstance(
                asyncio.get_event_loop_policy(), asyncio.WindowsProactorEventLoopPolicy  # type: ignore
            ):
                warnings.warn(WINDOWS_WARN)

    @property
    def acurl(self):
        if self.loop is None:
            self.loop = asyncio.get_running_loop()
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
        allow_redirects: bool = True,
        max_redirects: Optional[int] = None,
        proxies: Optional[dict] = None,
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
        req, buffer, header_buffer, q, header_recved, quit_now = self._set_curl_options(
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
