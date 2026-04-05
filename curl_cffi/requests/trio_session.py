import sys
from collections.abc import Callable
from contextlib import asynccontextmanager, suppress
from io import BytesIO
from typing import Literal, Optional, TypeVar, Union, cast

try:
    import trio
except ImportError as exc:  # pragma: no cover - imported only when trio is needed.
    raise ImportError(
        "Trio support requires the 'trio' package. Install it with: pip install trio"
    ) from exc

from ..const import CurlHttpVersion
from ..curl import Curl, CurlError, CurlMime
from ..trio import TrioAsyncCurl, TrioTask
from .cookies import CookieTypes
from .exceptions import RequestException, code2error
from .headers import HeaderTypes
from .impersonate import BrowserTypeLiteral, ExtraFingerprints, ExtraFpDict
from .models import STREAM_END, Response
from .session import (
    BaseSession,
    BaseSessionParams,
    HttpMethod,
    ProxySpec,
    RequestParams,
    StreamRequestParams,
    Unpack,
)
from .utils import HttpVersionLiteral, not_set, set_curl_options

_NO_PEEK = object()

R = TypeVar("R", bound=Response)


class TrioQueue:
    def __init__(self) -> None:
        self._send, self._recv = trio.open_memory_channel(sys.maxsize)
        self._peeked = _NO_PEEK

    def put_nowait(self, item) -> None:
        try:
            self._send.send_nowait(item)
        except trio.WouldBlock:
            trio.lowlevel.spawn_system_task(self._send.send, item)

    async def put(self, item) -> None:
        await self._send.send(item)

    async def get(self):
        if self._peeked is not _NO_PEEK:
            item = self._peeked
            self._peeked = _NO_PEEK
            return item
        return await self._recv.receive()

    def peek(self, default=None):
        if self._peeked is not _NO_PEEK:
            return self._peeked
        try:
            self._peeked = self._recv.receive_nowait()
        except (trio.WouldBlock, trio.EndOfChannel):
            return default
        return self._peeked


class TrioSession(BaseSession[R]):
    """A Trio request session, cookies and connections will be reused."""

    def __init__(
        self,
        *,
        async_curl: Optional[TrioAsyncCurl] = None,
        max_clients: int = 10,
        **kwargs: Unpack[BaseSessionParams],
    ):
        """
        Parameters set in the ``__init__`` method will be override by the same parameter
        in request method.

        Args:
            async_curl: TrioAsyncCurl object to use.
            max_clients: maximum curl handle to use in the session,
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

        .. code-block:: python

            import trio
            from curl_cffi.requests import TrioSession

            async def main():
                async with TrioSession() as s:
                    r = await s.get("https://example.com")

            trio.run(main)
        """
        super().__init__(**kwargs)
        self._acurl = async_curl
        self.max_clients = max_clients
        self.init_pool()

    @property
    def acurl(self) -> TrioAsyncCurl:
        if self._acurl is None:
            self._acurl = TrioAsyncCurl()
        return self._acurl

    def init_pool(self) -> None:
        self._pool_send, self._pool_recv = trio.open_memory_channel(self.max_clients)
        for _ in range(self.max_clients):
            self._pool_send.send_nowait(None)

    async def pop_curl(self) -> Curl:
        curl = await self._pool_recv.receive()
        if curl is None:
            curl = Curl(debug=self.debug)
        return curl

    def push_curl(self, curl) -> None:
        with suppress(trio.WouldBlock):
            self._pool_send.send_nowait(curl)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
        return None

    async def close(self) -> None:
        await self.acurl.close()
        self._closed = True
        while True:
            try:
                curl = self._pool_recv.receive_nowait()
            except (trio.WouldBlock, trio.EndOfChannel):
                break
            if curl:
                curl.close()

    def release_curl(self, curl) -> None:
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
    ):
        """Equivalent to ``async with request(..., stream=True) as r:``"""
        rsp = await self.request(method=method, url=url, **kwargs, stream=True)
        try:
            yield rsp
        finally:
            await rsp.aclose()

    async def ws_connect(self, *args, **kwargs):
        self._check_session_closed()
        raise NotImplementedError(
            "TrioSession does not support WebSocket yet. "
            "Use AsyncSession for asyncio websockets."
        )

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
        timeout: Optional[Union[float, tuple[float, float], object]] = not_set,
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
            timeout=self.timeout if timeout is not_set else timeout,
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
            queue_class=TrioQueue,
            event_class=trio.Event,
        )

        if stream:
            task = self.acurl.add_handle(curl)

            async def perform():
                try:
                    await task
                except CurlError as e:
                    rsp = self._parse_response(
                        curl, buffer, header_buffer, default_encoding, discard_cookies
                    )
                    rsp.request = req
                    q.put_nowait(RequestException(str(e), e.code, rsp))  # type: ignore
                finally:
                    if not cast(trio.Event, header_recved).is_set():
                        cast(trio.Event, header_recved).set()
                    await q.put(STREAM_END)  # type: ignore

            stream_task = TrioTask(perform())

            await cast(trio.Event, header_recved).wait()
            rsp = self._parse_response(
                curl, buffer, header_buffer, default_encoding, discard_cookies
            )

            first_element = q.peek(_NO_PEEK)  # type: ignore
            if isinstance(first_element, RequestException):
                self.release_curl(curl)
                raise first_element

            def cleanup(_task):
                self.release_curl(curl)

            stream_task.add_done_callback(cleanup)

            rsp.request = req
            rsp.astream_task = stream_task
            rsp.quit_now = quit_now
            rsp.queue = q
            if self.raise_for_status:
                rsp.raise_for_status()
            return rsp

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
