from __future__ import annotations

import asyncio
from select import select
import struct
from enum import IntEnum
from json import loads, dumps
from typing import Any, Callable, Optional, Tuple, TYPE_CHECKING, TypeVar, Union

from .utils import _set_curl_options, not_set
from ..const import CurlECode, CurlOpt, CurlWsFlag
from ..curl import Curl, CurlError

if TYPE_CHECKING:
    from typing_extensions import Self

    from .cookies import CookieTypes
    from .headers import HeaderTypes
    from .models import BrowserType
    from .session import ProxySpec
    from ..const import CurlHttpVersion
    from ..curl import CurlWsFrame

    T = TypeVar("T")

    ON_DATA_T = Callable[["WebSocket", bytes, CurlWsFrame], None]
    ON_MESSAGE_T = Callable[["WebSocket", Union[bytes, str]], None]
    ON_ERROR_T = Callable[["WebSocket", CurlError], None]
    ON_OPEN_T = Callable[["WebSocket"], None]
    ON_CLOSE_T = Callable[["WebSocket", int, str], None]


class WsCloseCode(IntEnum):
    OK = 1000
    GOING_AWAY = 1001
    PROTOCOL_ERROR = 1002
    UNSUPPORTED_DATA = 1003
    UNKNOWN = 1005
    ABNORMAL_CLOSURE = 1006
    INVALID_DATA = 1007
    POLICY_VIOLATION = 1008
    MESSAGE_TOO_BIG = 1009
    MANDATORY_EXTENSION = 1010
    INTERNAL_ERROR = 1011
    SERVICE_RESTART = 1012
    TRY_AGAIN_LATER = 1013
    BAD_GATEWAY = 1014


class WebSocketError(CurlError):
    pass


class BaseWebSocket:
    def __init__(self, curl: Curl, *, autoclose: bool = True):
        self.curl: Curl = curl
        self.autoclose: bool = autoclose
        self._close_code: Optional[int] = None
        self._close_reason: Optional[str] = None

    @property
    def closed(self) -> bool:
        """Whether the WebSocket is closed."""
        return self.curl is not_set

    @property
    def close_code(self) -> Optional[int]:
        """The WebSocket close code, if the connection is closed."""
        return self._close_code

    @property
    def close_reason(self) -> Optional[str]:
        """The WebSocket close reason, if the connection is closed."""
        return self._close_reason

    @staticmethod
    def _pack_close_frame(code: int, reason: bytes) -> bytes:
        return struct.pack("!H", code) + reason

    @staticmethod
    def _unpack_close_frame(frame: bytes) -> Tuple[int, str]:
        if len(frame) < 2:
            code = WsCloseCode.UNKNOWN
            reason = ""
        else:
            try:
                code = struct.unpack_from("!H", frame)[0]
                reason = frame[2:].decode()
            except UnicodeDecodeError:
                raise WebSocketError("Invalid close message", WsCloseCode.INVALID_DATA)
            except Exception:
                raise WebSocketError("Invalid close frame", WsCloseCode.PROTOCOL_ERROR)
            else:
                if code < 3000 and (code not in WsCloseCode or code == 1005):
                    raise WebSocketError("Invalid close code", WsCloseCode.PROTOCOL_ERROR)
        return code, reason

    def terminate(self):
        """Terminate the underlying connection."""
        if self.curl is not_set:
            return
        self.curl.close()
        self.curl = not_set


class WebSocket(BaseWebSocket):
    """A WebSocket implementation using libcurl."""

    def __init__(
        self,
        *,
        autoclose: bool = True,
        skip_utf8_validation: bool = False,
        debug: bool = False,
        on_open: Optional[ON_OPEN_T] = None,
        on_close: Optional[ON_CLOSE_T] = None,
        on_data: Optional[ON_DATA_T] = None,
        on_message: Optional[ON_MESSAGE_T] = None,
        on_error: Optional[ON_ERROR_T] = None,
    ):
        """
        Parameters:
            autoclose: whether to close the WebSocket after receiving a close frame.
            skip_utf8_validation: whether to skip UTF-8 validation for text frames in run_forever().
            debug: print extra curl debug info.
            on_open: callback to receive open events.
                The callback should accept one argument: WebSocket.
            on_close: callback to receive close events.
                The callback should accept three arguments: WebSocket, int, and str.
            on_data: callback to receive raw data frames.
                The callback should accept three arguments: WebSocket, bytes, and CurlWsFrame.
            on_message: callback to receive text frames.
                The callback should accept two arguments: WebSocket and Union[bytes, str].
            on_error: callback to receive errors.
                The callback should accept two arguments: WebSocket and CurlError.
        """
        super().__init__(not_set, autoclose=autoclose)
        self.skip_utf8_validation = skip_utf8_validation
        self.debug = debug

        self._emitters: dict[str, Callable] = {}
        if on_open:
            self._emitters["open"] = on_open
        if on_close:
            self._emitters["close"] = on_close
        if on_data:
            self._emitters["data"] = on_data
        if on_message:
            self._emitters["message"] = on_message
        if on_error:
            self._emitters["error"] = on_error

    def __iter__(self) -> WebSocket:
        if self.closed:
            raise TypeError("WebSocket is closed")
        return self

    def __next__(self) -> bytes:
        msg, flags = self.recv()
        if flags & CurlWsFlag.CLOSE:
            raise StopIteration
        return msg

    def _emit(self, event_type: str, *args) -> None:
        callback = self._emitters.get(event_type)
        if callback:
            try:
                callback(self, *args)
            except Exception as e:
                error_callback = self._emitters.get("error")
                if error_callback:
                    error_callback(self, e)

    def connect(
        self,
        url: str,
        *,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[Tuple[str, str]] = None,
        timeout: Optional[Union[float, Tuple[float, float]]] = None,
        allow_redirects: bool = True,
        max_redirects: int = -1,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[Tuple[str, str]] = None,
        verify: Optional[Union[bool, str]] = True,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        impersonate: Optional[Union[str, BrowserType]] = None,
        default_headers: bool = True,
        curl_options: Optional[dict] = None,
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        max_recv_speed: int = 0,
    ):
        """Connect to the WebSocket.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html

        Parameters:
            url: url for the requests.
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
        if not self.closed:
            raise TypeError("WebSocket is already connected")

        if proxy and proxies:
            raise TypeError("Cannot specify both 'proxy' and 'proxies'")
        if proxy:
            proxies = {"all": proxy}

        self.curl = curl = Curl(debug=self.debug)
        _set_curl_options(
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
            proxy_auth=proxy_auth,
            verify=verify,
            referer=referer,
            accept_encoding=accept_encoding,
            impersonate=impersonate,
            default_headers=default_headers,
            curl_options=curl_options,
            http_version=http_version,
            interface=interface,
            max_recv_speed=max_recv_speed,
        )

        # https://curl.se/docs/websocket.html
        curl.setopt(CurlOpt.CONNECT_ONLY, 2)
        curl.perform()

    def recv_fragment(self) -> Tuple[bytes, CurlWsFrame]:
        """Receive a single frame as bytes."""
        if self.closed:
            raise TypeError("WebSocket is closed")

        chunk, frame = self.curl.ws_recv()
        if frame.flags & CurlWsFlag.CLOSE:
            try:
                self._close_code, self._close_reason = self._unpack_close_frame(chunk)
            except WebSocketError as e:
                # Follow the spec to close the connection
                # Errors do not respect autoclose
                self._close_code = e.code
                self.close(e.code)
                raise
            if self.autoclose:
                self.close()

        return chunk, frame

    def recv(self) -> Tuple[bytes, int]:
        """
        Receive a frame as bytes.

        libcurl split frames into fragments, so we have to collect all the chunks for
        a frame.
        """
        chunks = []
        flags = 0
        # TODO use select here
        while True:
            try:
                chunk, frame = self.recv_fragment()
                flags = frame.flags
                chunks.append(chunk)
                if frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0:
                    break
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    pass
                else:
                    raise

        return b"".join(chunks), flags

    def recv_str(self) -> str:
        """Receive a text frame."""
        data, flags = self.recv()
        if not flags & CurlWsFlag.TEXT:
            raise TypeError("Received non-text frame")
        return data.decode()

    def recv_json(self, *, loads: Callable[[str], T] = loads) -> T:
        """Receive a JSON frame."""
        data = self.recv_str()
        return loads(data)

    def send(self, payload: Union[str, bytes], flags: CurlWsFlag = CurlWsFlag.BINARY):
        """Send a data frame."""
        if self.closed:
            raise TypeError("WebSocket is closed")

        # curl expects bytes
        if isinstance(payload, str):
            payload = payload.encode()
        return self.curl.ws_send(payload, flags)

    def send_binary(self, payload: bytes):
        """Send a binary frame."""
        return self.send(payload, CurlWsFlag.BINARY)

    def send_bytes(self, payload: bytes):
        """Send a binary frame."""
        return self.send(payload, CurlWsFlag.BINARY)

    def send_str(self, payload: str):
        """Send a text frame."""
        return self.send(payload, CurlWsFlag.TEXT)

    def send_json(self, payload: Any, *, dumps: Callable[[Any], str] = dumps):
        """Send a JSON frame."""
        return self.send_str(dumps(payload))

    def ping(self, payload: Union[str, bytes]):
        """Send a ping frame."""
        return self.send(payload, CurlWsFlag.PING)

    def run_forever(self, url: str, **kwargs):
        """
        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html
        """
        if not self.closed:
            raise TypeError("WebSocket is already connected")

        self.connect(url, **kwargs)
        self._emit("open")

        # Keep reading the messages and invoke callbacks
        # TODO: Reconnect logic
        chunks = []
        keep_running = True
        while keep_running:
            try:
                msg, frame = self.recv_fragment()
                flags = frame.flags
                self._emit("data", msg, frame)

                if not (frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0):
                    chunks.append(msg)
                    continue

                # Avoid unnecessary computation
                if "message" in self._emitters:
                    if (flags & CurlWsFlag.TEXT) and not self.skip_utf8_validation:
                        try:
                            msg = msg.decode()
                        except UnicodeDecodeError:
                            self._close_code = WsCloseCode.INVALID_DATA
                            self.close(WsCloseCode.INVALID_DATA)
                            raise WebSocketError("Invalid UTF-8", WsCloseCode.INVALID_DATA)
                    if (flags & CurlWsFlag.BINARY) or (flags & CurlWsFlag.TEXT):
                        self._emit("message", msg)
                if flags & CurlWsFlag.CLOSE:
                    keep_running = False
                    self._emit("close", self._close_code or 0, self._close_reason or "")
            except CurlError as e:
                self._emit("error", e)
                if e.code == CurlECode.AGAIN:
                    pass
                else:
                    if not self.closed:
                        code = 1000
                        if isinstance(e, WebSocketError):
                            code = e.code
                        self.close(code)
                    raise

    def close(self, code: int = WsCloseCode.OK, message: bytes = b""):
        """Close the connection."""
        if self.curl is not_set:
            return

        # TODO: As per spec, we should wait for the server to close the connection
        # But this is not a requirement
        msg = self._pack_close_frame(code, message)
        self.send(msg, CurlWsFlag.CLOSE)
        # The only way to close the connection appears to be curl_easy_cleanup
        # But this renders the curl handle unusable, so we do not push it back to the pool
        self.terminate()


class AsyncWebSocket(BaseWebSocket):
    """A pseudo-async WebSocket implementation using libcurl."""

    def __init__(self, curl: Curl, *, autoclose: bool = True):
        super().__init__(curl, autoclose=autoclose)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._recv_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()

    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def __aiter__(self) -> Self:
        if self.closed:
            raise TypeError("WebSocket is closed")
        return self

    async def __anext__(self) -> bytes:
        msg, flags = await self.recv()
        if flags & CurlWsFlag.CLOSE:
            raise StopAsyncIteration
        return msg

    async def recv_fragment(self, *, timeout: Optional[float] = None) -> Tuple[bytes, CurlWsFrame]:
        """Receive a single frame as bytes."""
        if self.closed:
            raise TypeError("WebSocket is closed")
        if self._recv_lock.locked():
            raise TypeError("Concurrent call to recv_fragment() is not allowed")

        async with self._recv_lock:
            chunk, frame = await asyncio.wait_for(self.loop.run_in_executor(None, self.curl.ws_recv), timeout)
            if frame.flags & CurlWsFlag.CLOSE:
                try:
                    self._close_code, self._close_reason = self._unpack_close_frame(chunk)
                except WebSocketError as e:
                    # Follow the spec to close the connection
                    # Errors do not respect autoclose
                    self._close_code = e.code
                    await self.close(e.code)
                    raise
                if self.autoclose:
                    await self.close()

        return chunk, frame

    async def recv(self, *, timeout: Optional[float] = None) -> Tuple[bytes, int]:
        """
        Receive a frame as bytes.

        libcurl split frames into fragments, so we have to collect all the chunks for
        a frame.
        """
        chunks = []
        flags = 0
        # TODO use select here
        while True:
            try:
                chunk, frame = await self.recv_fragment(timeout=timeout)
                flags = frame.flags
                chunks.append(chunk)
                if frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0:
                    break
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    pass
                else:
                    raise

        return b"".join(chunks), flags

    async def recv_str(self, *, timeout: Optional[float] = None) -> str:
        """Receive a text frame."""
        data, flags = await self.recv(timeout=timeout)
        if not flags & CurlWsFlag.TEXT:
            raise TypeError("Received non-text frame")
        return data.decode()

    async def recv_json(self, *, loads: Callable[[str], T] = loads, timeout: Optional[float] = None) -> T:
        """Receive a JSON frame."""
        data = await self.recv_str(timeout=timeout)
        return loads(data)

    async def send(self, payload: Union[str, bytes], flags: CurlWsFlag = CurlWsFlag.BINARY):
        """Send a data frame."""
        if self.closed:
            raise TypeError("WebSocket is closed")

        # curl expects bytes
        if isinstance(payload, str):
            payload = payload.encode()
        async with self._send_lock:  # TODO: Why does concurrently sending fail
            return await self.loop.run_in_executor(None, self.curl.ws_send, payload, flags)

    async def send_binary(self, payload: bytes):
        """Send a binary frame."""
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_bytes(self, payload: bytes):
        """Send a binary frame."""
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_str(self, payload: str):
        """Send a text frame."""
        return await self.send(payload, CurlWsFlag.TEXT)

    async def send_json(self, payload: Any, *, dumps: Callable[[Any], str] = dumps):
        """Send a JSON frame."""
        return await self.send_str(dumps(payload))

    async def ping(self, payload: Union[str, bytes]):
        """Send a ping frame."""
        return await self.send(payload, CurlWsFlag.PING)

    async def close(self, code: int = WsCloseCode.OK, message: bytes = b""):
        """Close the connection."""
        if self.curl is not_set:
            return

        # TODO: As per spec, we should wait for the server to close the connection
        # But this is not a requirement
        msg = self._pack_close_frame(code, message)
        await self.send(msg, CurlWsFlag.CLOSE)
        # The only way to close the connection appears to be curl_easy_cleanup
        # But this renders the curl handle unusable, so we do not push it back to the pool
        self.terminate()
