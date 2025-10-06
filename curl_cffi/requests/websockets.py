from __future__ import annotations

import asyncio
import struct
import warnings
from collections.abc import AsyncIterable, Iterable
from enum import IntEnum
from functools import partial
from json import dumps, loads
from select import select
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Literal,
    Optional,
    TypeVar,
    Union,
)

from typing_extensions import override

from curl_cffi.requests import Response
from curl_cffi.utils import CurlCffiWarning

from ..aio import CURL_SOCKET_BAD, get_selector
from ..const import CurlECode, CurlInfo, CurlOpt, CurlWsFlag
from ..curl import Curl, CurlError
from .exceptions import SessionClosed, Timeout
from .utils import not_set, set_curl_options

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..const import CurlHttpVersion
    from ..curl import CurlWsFrame
    from .cookies import CookieTypes
    from .headers import HeaderTypes
    from .impersonate import BrowserTypeLiteral, ExtraFingerprints, ExtraFpDict
    from .session import AsyncSession, ProxySpec

    T = TypeVar("T")

    ON_DATA_T = Callable[["WebSocket", bytes, CurlWsFrame], None]
    ON_MESSAGE_T = Callable[["WebSocket", Union[bytes, str]], None]
    ON_ERROR_T = Callable[["WebSocket", CurlError], None]
    ON_OPEN_T = Callable[["WebSocket"], None]
    ON_CLOSE_T = Callable[["WebSocket", int, str], None]
    WS_QUEUE_ITEM = tuple[Union[bytes, Exception], int]


# We need a partial for dumps() because a custom function may not accept the parameter
dumps = partial(dumps, separators=(",", ":"))


class WsCloseCode(IntEnum):
    """See: https://www.iana.org/assignments/websocket/websocket.xhtml"""

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
    TLS_HANDSHAKE = 1015
    UNAUTHORIZED = 3000
    FORBIDDEN = 3003
    TIMEOUT = 3008


class WebSocketError(CurlError):
    """WebSocket-specific error."""

    def __init__(
        self, message: str, code: Union[WsCloseCode, CurlECode, Literal[0]] = 0
    ):
        super().__init__(message, code)  # type: ignore


class WebSocketClosed(WebSocketError, SessionClosed):
    """WebSocket is already closed."""


class WebSocketTimeout(WebSocketError, Timeout):
    """WebSocket operation timed out."""


class BaseWebSocket:
    def __init__(self, curl: Curl, *, autoclose: bool = True, debug: bool = False):
        self._curl: Curl = curl
        self.autoclose: bool = autoclose
        self._close_code: Optional[int] = None
        self._close_reason: Optional[str] = None
        self.debug = debug
        self.closed = False

    @property
    def curl(self):
        if self._curl is not_set:
            self._curl = Curl(debug=self.debug)
        return self._curl

    @property
    def close_code(self) -> Optional[int]:
        """The WebSocket close code, if the connection has been closed."""
        return self._close_code

    @property
    def close_reason(self) -> Optional[str]:
        """The WebSocket close reason, if the connection has been closed."""
        return self._close_reason

    @staticmethod
    def _pack_close_frame(code: int, reason: bytes) -> bytes:
        return struct.pack("!H", code) + reason

    @staticmethod
    def _unpack_close_frame(frame: bytes) -> tuple[int, str]:
        if len(frame) < 2:
            code = WsCloseCode.UNKNOWN
            reason = ""
        else:
            try:
                code = struct.unpack_from("!H", frame)[0]
                reason = frame[2:].decode()
            except UnicodeDecodeError as e:
                raise WebSocketError(
                    "Invalid close message", WsCloseCode.INVALID_DATA
                ) from e
            except Exception as e:
                raise WebSocketError(
                    "Invalid close frame", WsCloseCode.PROTOCOL_ERROR
                ) from e
            else:
                if (
                    code not in WsCloseCode._value2member_map_
                    or code == WsCloseCode.UNKNOWN
                ):
                    raise WebSocketError(
                        f"Invalid close code: {code}", WsCloseCode.PROTOCOL_ERROR
                    )
        return code, reason

    def terminate(self):
        """Terminate the underlying connection."""
        self.closed = True
        self.curl.close()


EventTypeLiteral = Literal["open", "close", "data", "message", "error"]


class WebSocket(BaseWebSocket):
    """A WebSocket implementation using libcurl."""

    def __init__(
        self,
        curl: Union[Curl, Any] = not_set,
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
        Args:
            autoclose: whether to close the WebSocket after receiving a close frame.
            skip_utf8_validation: whether to skip UTF-8 validation for text frames in
                run_forever().
            debug: print extra curl debug info.

            on_open: open callback, ``def on_open(ws)``
            on_close: close callback, ``def on_close(ws, code, reason)``
            on_data: raw data receive callback, ``def on_data(ws, data, frame)``
            on_message: message receive callback, ``def on_message(ws, message)``
            on_error: error callback, ``def on_error(ws, exception)``
        """
        super().__init__(curl=curl, autoclose=autoclose, debug=debug)
        self.skip_utf8_validation = skip_utf8_validation

        self._emitters: dict[EventTypeLiteral, Callable] = {}
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
            raise WebSocketClosed("WebSocket is closed")
        return self

    def __next__(self) -> bytes:
        msg, flags = self.recv()
        if flags & CurlWsFlag.CLOSE:
            raise StopIteration
        return msg

    def _emit(self, event_type: EventTypeLiteral, *args) -> None:
        callback = self._emitters.get(event_type)
        if callback:
            try:
                callback(self, *args)
            except Exception as e:
                error_callback = self._emitters.get("error")
                if error_callback:
                    error_callback(self, e)
                else:
                    warnings.warn(
                        f"WebSocket callback '{event_type}' failed",
                        CurlCffiWarning,
                        stacklevel=2,
                    )

    def connect(
        self,
        url: str,
        params: Optional[Union[dict, list, tuple]] = None,
        headers: Optional[HeaderTypes] = None,
        cookies: Optional[CookieTypes] = None,
        auth: Optional[tuple[str, str]] = None,
        timeout: Optional[Union[float, tuple[float, float], object]] = not_set,
        allow_redirects: bool = True,
        max_redirects: int = 30,
        proxies: Optional[ProxySpec] = None,
        proxy: Optional[str] = None,
        proxy_auth: Optional[tuple[str, str]] = None,
        verify: Optional[bool] = None,
        referer: Optional[str] = None,
        accept_encoding: Optional[str] = "gzip, deflate, br",
        impersonate: Optional[BrowserTypeLiteral] = None,
        ja3: Optional[str] = None,
        akamai: Optional[str] = None,
        extra_fp: Optional[Union[ExtraFingerprints, ExtraFpDict]] = None,
        default_headers: bool = True,
        quote: Union[str, Literal[False]] = "",
        http_version: Optional[CurlHttpVersion] = None,
        interface: Optional[str] = None,
        cert: Optional[Union[str, tuple[str, str]]] = None,
        max_recv_speed: int = 0,
        curl_options: Optional[dict[CurlOpt, str]] = None,
    ):
        """Connect to the WebSocket.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html

        Args:
            url: url for the requests.
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
            default_encoding: encoding for decoding response content if charset is not
                found in headers. Defaults to "utf-8". Can be set to a callable for
                automatic detection.
            quote: Set characters to be quoted, i.e. percent-encoded. Default safe
                string is ``!#$%&'()*+,/:;=?@[]~``. If set to a sting, the character
                will be removed from the safe string, thus quoted. If set to False, the
                url will be kept as is, without any automatic percent-encoding, you must
                encode the URL yourself.
            curl_options: extra curl options to use.
            http_version: limiting http version, defaults to http2.
            interface: which interface to use.
            cert: a tuple of (cert, key) filenames for client cert.
            max_recv_speed: maximum receive speed, bytes per second.
            curl_options: extra curl options to use.
        """

        curl = self.curl

        set_curl_options(
            curl=curl,
            method="GET",
            url=url,
            params_list=[None, params],
            headers_list=[None, headers],
            cookies_list=[None, cookies],
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            max_redirects=max_redirects,
            proxies_list=[None, proxies],
            proxy=proxy,
            proxy_auth=proxy_auth,
            verify_list=[None, verify],
            referer=referer,
            accept_encoding=accept_encoding,
            impersonate=impersonate,
            ja3=ja3,
            akamai=akamai,
            extra_fp=extra_fp,
            default_headers=default_headers,
            quote=quote,
            http_version=http_version,
            interface=interface,
            max_recv_speed=max_recv_speed,
            cert=cert,
            curl_options=curl_options,
        )

        # Magic number defined in: https://curl.se/docs/websocket.html
        curl.setopt(CurlOpt.CONNECT_ONLY, 2)
        curl.perform()
        return self

    def recv_fragment(self) -> tuple[bytes, CurlWsFrame]:
        """Receive a single curl websocket fragment as bytes."""

        if self.closed:
            raise WebSocketClosed("WebSocket is already closed")

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

    def recv(self) -> tuple[bytes, int]:
        """
        Receive a frame as bytes. libcurl splits frames into fragments, so we have to
        collect all the chunks for a frame.
        """
        chunks = []
        flags = 0

        sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE
            )

        while True:
            try:
                # Try to receive the first fragment first
                chunk, frame = self.recv_fragment()
                flags = frame.flags
                chunks.append(chunk)
                if frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0:
                    break
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    # According to https://curl.se/libcurl/c/curl_ws_recv.html
                    # > in real application: wait for socket here, e.g. using select()
                    _, _, _ = select([sock_fd], [], [], 0.5)
                else:
                    raise

        return b"".join(chunks), flags

    def recv_str(self) -> str:
        """Receive a text frame."""
        data, flags = self.recv()
        if not (flags & CurlWsFlag.TEXT):
            raise WebSocketError("Not valid text frame", WsCloseCode.INVALID_DATA)
        return data.decode()

    def recv_json(self, *, loads: Callable[[str], T] = loads) -> T:
        """Receive a JSON frame.

        Args:
            loads: JSON decoder, default is json.loads.
        """
        data = self.recv_str()
        return loads(data)

    def send(
        self,
        payload: Union[str, bytes, memoryview],
        flags: CurlWsFlag = CurlWsFlag.BINARY,
    ):
        """Send a data frame.

        Args:
            payload: data to send.
            flags: flags for the frame.
        """
        if flags & CurlWsFlag.CLOSE:
            self.keep_running = False

        if self.closed:
            raise WebSocketClosed("WebSocket is already closed")

        # curl expects bytes
        if isinstance(payload, str):
            payload = payload.encode()

        sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE
            )

        # Loop checks for CurlECode.Again
        # https://curl.se/libcurl/c/curl_ws_send.html
        offset = 0
        while offset < len(payload):
            current_buffer = payload[offset:]

            try:
                n_sent = self.curl.ws_send(current_buffer, flags)
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    _, writeable, _ = select([], [sock_fd], [], 0.5)
                    if not writeable:
                        raise WebSocketError("Socket write timeout") from e
                    continue
                raise

            offset += n_sent

        return offset

    def send_binary(self, payload: bytes):
        """Send a binary frame.

        Args:
            payload: binary data to send.
        """
        return self.send(payload, CurlWsFlag.BINARY)

    def send_bytes(self, payload: bytes):
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: binary data to send.
        """
        return self.send(payload, CurlWsFlag.BINARY)

    def send_str(self, payload: str):
        """Send a text frame.

        Args:
            payload: text data to send.
        """
        return self.send(payload, CurlWsFlag.TEXT)

    def send_json(self, payload: Any, *, dumps: Callable[[Any], str] = dumps):
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is json.dumps.
        """
        return self.send_str(dumps(payload))

    def ping(self, payload: Union[str, bytes]):
        """Send a ping frame.

        Args:
            payload: data to send.
        """
        return self.send(payload, CurlWsFlag.PING)

    def run_forever(self, url: str = "", **kwargs):
        """Run the WebSocket forever. See :meth:`connect` for details on parameters.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html
        """

        if url:
            self.connect(url, **kwargs)

        sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE
            )

        self._emit("open")

        # Keep reading the messages and invoke callbacks
        # TODO: Reconnect logic
        chunks = []
        self.keep_running = True
        while self.keep_running:
            try:
                chunk, frame = self.recv_fragment()
                flags = frame.flags
                self._emit("data", chunk, frame)

                chunks.append(chunk)
                if not (frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0):
                    continue

                # Avoid unnecessary computation
                if "message" in self._emitters:
                    # Concatenate collected chunks with the final message
                    msg = b"".join(chunks)

                    if (flags & CurlWsFlag.TEXT) and not self.skip_utf8_validation:
                        try:
                            msg = msg.decode()  # type: ignore
                        except UnicodeDecodeError as e:
                            self._close_code = WsCloseCode.INVALID_DATA
                            self.close(WsCloseCode.INVALID_DATA)
                            raise WebSocketError(
                                "Invalid UTF-8", WsCloseCode.INVALID_DATA
                            ) from e

                    if (flags & CurlWsFlag.BINARY) or (flags & CurlWsFlag.TEXT):
                        self._emit("message", msg)

                chunks = []  # Reset chunks for next message

                if flags & CurlWsFlag.CLOSE:
                    self.keep_running = False
                    self._emit("close", self._close_code or 0, self._close_reason or "")

            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    _, _, _ = select([sock_fd], [], [], 0.5)
                else:
                    self._emit("error", e)
                    if not self.closed:
                        code = WsCloseCode.UNKNOWN
                        if isinstance(e, WebSocketError):
                            code = e.code
                        self.close(code)
                    raise

    def close(self, code: int = WsCloseCode.OK, message: bytes = b""):
        """Close the connection.

        Args:
            code: close code.
            message: close reason.
        """
        if self.curl is not_set:
            return

        # TODO: As per spec, we should wait for the server to close the connection
        # But this is not a requirement
        msg = self._pack_close_frame(code, message)
        self.send(msg, CurlWsFlag.CLOSE)
        # The only way to close the connection appears to be curl_easy_cleanup
        self.terminate()


class AsyncWebSocket(BaseWebSocket):
    """
    An async WebSocket implementation using libcurl.

    Note: This object represents a single WebSocket connection. Once closed,
    it cannot be reopened. A new instance must be created to reconnect.
    """

    _YIELD_CHECK_INTERVAL: ClassVar[int] = 63
    _BATCHING_YIELD_INTERVAL: ClassVar[int] = 127
    _YIELD_INTERVAL_S: ClassVar[float] = 0.001
    _MAX_CURL_FRAME_SIZE: ClassVar[int] = 1024 * 1024
    _CURL_BUFSIZE: ClassVar[int] = 2 * 1024 * 1024

    def __init__(
        self,
        session: AsyncSession,
        curl: Curl,
        *,
        autoclose: bool = True,
        debug: bool = False,
        queue_size: int = 4096,
        max_send_batch_size: int = 256,
        max_batching_delay: float = 0.005,
        coalesce_frames: bool = False,
    ) -> None:
        super().__init__(curl=curl, autoclose=autoclose, debug=debug)
        self.session: AsyncSession[Response] = session
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sock_fd: int = -1
        self._send_lock: asyncio.Lock = asyncio.Lock()
        self._close_lock: asyncio.Lock = asyncio.Lock()
        self._read_task: Optional[asyncio.Task[None]] = None
        self._write_task: Optional[asyncio.Task[None]] = None
        self._receive_queue: asyncio.Queue[WS_QUEUE_ITEM] = asyncio.Queue(
            maxsize=queue_size
        )
        self._send_queue: asyncio.Queue[WS_QUEUE_ITEM] = asyncio.Queue(
            maxsize=queue_size
        )
        self._max_send_batch_size: int = max_send_batch_size
        self._max_batching_delay: float = max_batching_delay
        self._coalesce_frames: bool = coalesce_frames

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = get_selector(asyncio.get_running_loop())
        return self._loop

    def __aiter__(self) -> Self:
        if self.closed:
            raise WebSocketClosed("WebSocket has been closed")
        self._start_io_tasks()
        return self

    async def __anext__(self) -> bytes:
        msg, flags = await self.recv()
        if (msg is None) or (flags & CurlWsFlag.CLOSE):
            raise StopAsyncIteration
        return msg

    def _start_io_tasks(self) -> None:
        """Start the read/write loop async tasks and set buffer size.

        Raises:
            WebSocketError: The WebSocket FD was invalid.
        """

        # Return early if already started
        if self._read_task is not None:
            return

        # Get the currently active socket FD
        self._sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if self._sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket.", code=CurlECode.NO_CONNECTION_AVAILABLE
            )

        self.curl.setopt(CurlOpt.BUFFERSIZE, self._CURL_BUFSIZE)
        self._read_task = self.loop.create_task(self._read_loop())
        self._write_task = self.loop.create_task(self._write_loop())

    async def recv(
        self, *, timeout: Optional[float] = None
    ) -> tuple[Optional[bytes], int]:
        """Receive a frame as bytes. libcurl splits frames into fragments, so we have
        to collect all the chunks for a frame. This is a lightweight call that awaits
        the next item from the receive queue, which will contain a full frame.
        The actual blocking processing is done cooperatively in the `_read_loop` task.

        Args:
            timeout: how many seconds to wait before giving up.

        Raises:
            WebSocketClosed: Read called on a closed WebSocket.
            WebSocketTimeout: Timed out waiting for WebSocket frame.
            result: A WebSocket exception that was picked up in the receive queue.

        Returns:
            tuple[bytes, int]: A tuple with the received payload and flags.
        """
        if self.closed and self._receive_queue.empty():
            raise WebSocketClosed("WebSocket is closed")
        self._start_io_tasks()
        try:
            result, flags = await asyncio.wait_for(self._receive_queue.get(), timeout)
            if isinstance(result, Exception):
                raise result
            return result, flags
        except asyncio.TimeoutError as e:
            raise WebSocketTimeout(
                "WebSocket recv() timed out", CurlECode.OPERATION_TIMEDOUT
            ) from e

    async def recv_str(self, *, timeout: Optional[float] = None) -> str:
        """Receive a text frame.

        Args:
            timeout: how many seconds to wait before giving up.
        """
        data, flags = await self.recv(timeout=timeout)
        if data is None or not (flags & CurlWsFlag.TEXT):
            raise WebSocketError("Not a valid text frame", WsCloseCode.INVALID_DATA)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise WebSocketError(
                "Invalid UTF-8 in text frame", WsCloseCode.INVALID_DATA
            ) from e

    async def recv_json(
        self,
        *,
        loads: Callable[[Union[str, bytes]], T] = loads,
        timeout: Optional[float] = None,
    ) -> T:
        """Receive a JSON frame.

        Args:
            loads: JSON decoder, default is json.loads.
            timeout: how many seconds to wait before giving up.
        """
        data, flags = await self.recv(timeout=timeout)
        if data is None:
            raise WebSocketError(
                "Received empty frame, cannot decode JSON", WsCloseCode.INVALID_DATA
            )
        if flags & CurlWsFlag.TEXT:
            try:
                return loads(data.decode("utf-8"))
            except UnicodeDecodeError as e:
                raise WebSocketError(
                    "Invalid UTF-8 in JSON text frame", WsCloseCode.INVALID_DATA
                ) from e
        return loads(data)

    async def send(
        self, payload: Union[str, bytes], flags: CurlWsFlag = CurlWsFlag.BINARY
    ):
        """Send a data frame.
        Best for discrete messages and high volumes of small messages.
        It uses an adaptive batching writer for low latency and efficiency.
        This is a lightweight call which places the payload into the send queue.
        The message gets picked up by the `_write_loop` task and written into
        the WebSocket as soon as it is possible to do so.

        Args:
            payload: data to send.
            flags: flags for the frame.

        Raises:
            WebSocketClosed: The WebSocket is closed.
        """
        if self.closed:
            raise WebSocketClosed("WebSocket is closed")
        self._start_io_tasks()

        # curl expects bytes
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        await self._send_queue.put((payload, flags))

    async def send_binary(self, payload: bytes) -> None:
        """Send a binary frame.

        Args:
            payload: binary data to send.
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_bytes(self, payload: bytes) -> None:
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: binary data to send.
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_str(self, payload: str) -> None:
        """Send a text frame.

        Args:
            payload: text data to send.
        """
        return await self.send(payload, CurlWsFlag.TEXT)

    async def send_json(
        self, payload: Any, *, dumps: Callable[[Any], str] = dumps
    ) -> None:
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is json.dumps.
        """
        return await self.send_str(dumps(payload))

    async def ping(self, payload: Union[str, bytes]):
        """Send a ping frame.

        Args:
            payload: data to send.
        """
        return await self.send(payload, CurlWsFlag.PING)

    async def close(
        self, code: int = WsCloseCode.OK, message: bytes = b"", timeout: float = 5.0
    ) -> None:
        """Close the connection.

        Args:
            code (int, optional): Close code. Defaults to WsCloseCode.OK.
            message (bytes, optional): Close reason. Defaults to b"".
            timeout (float, optional): How long in seconds to wait closed.
        """
        async with self._close_lock:
            if self.closed:
                return

            self.closed = True

            # Gracefully send the close frame if the writer is still alive
            try:
                if self._write_task and not self._write_task.done():
                    close_frame = self._pack_close_frame(code, message)
                    await asyncio.wait_for(
                        self.send(close_frame, CurlWsFlag.CLOSE), timeout=timeout
                    )
                    await asyncio.wait_for(self.flush(), timeout=timeout)
            except (
                WebSocketError,
                WebSocketClosed,
                asyncio.TimeoutError,
                asyncio.CancelledError,
            ) as e:
                if self.debug:
                    warnings.warn(
                        f"Ignored exception during WebSocket close handshake: {e!r}",
                        CurlCffiWarning,
                        stacklevel=2,
                    )
            finally:
                self.terminate()

    @override
    def terminate(self) -> None:
        """Terminate the underlying connection."""
        stop_tasks: set[Union[asyncio.Task[None], None]] = {
            self._read_task,
            self._write_task,
        }

        # Cancel the tasks started in the I/O loop.
        for io_task in stop_tasks:
            if io_task and not io_task.done():
                io_task.cancel()

        # As a safety measure, deregister the reader/writers from the FD
        if self._sock_fd != -1:
            try:
                self.loop.remove_reader(self._sock_fd)
                self.loop.remove_writer(self._sock_fd)
            except (ValueError, OSError, KeyError):
                pass
            self._sock_fd = -1

        super().terminate()
        if self.session and not self.session._closed:
            # WebSocket curls CANNOT be reused
            self.session.push_curl(None)

    async def _read_loop(self) -> None:
        """The main asynchronous task for reading incoming WebSocket frames.

        This method runs a continuous loop that is responsible for all read
        operations from the underlying socket. It collects message fragments
        delivered by libcurl into a list and joins them to reconstruct the
        complete message, which is then placed onto the `_receive_queue`.

        The loop handles non-blocking I/O by listening for readability events
        on the socket file descriptor when a read operation would otherwise
        block (indicated by a `CurlError` with code `EAGAIN`).

        To ensure cooperative multitasking, the loop yields control to the
        asyncio event loop periodically, preventing it from starving other
        concurrent tasks during high message volumes.
        """
        chunks = []
        msg_counter = 0
        try:
            while not self.closed:
                start_time = self.loop.time()
                while True:
                    try:
                        chunk, frame = self._curl.ws_recv()
                        chunks.append(chunk)
                        if frame.bytesleft > 0 or (frame.flags & CurlWsFlag.CONT):
                            continue
                        message, flags = b"".join(chunks), frame.flags
                        chunks.clear()
                        msg_counter += 1
                        await self._receive_queue.put((message, flags))
                        if flags & CurlWsFlag.CLOSE:
                            self._handle_close_frame(message)
                            return
                        if (msg_counter & self._YIELD_CHECK_INTERVAL) == 0 and (
                            self.loop.time() - start_time > self._YIELD_INTERVAL_S
                        ):
                            await asyncio.sleep(0)
                            start_time = self.loop.time()
                    except CurlError as e:
                        if e.code == CurlECode.AGAIN:
                            break
                        await self._receive_queue.put((e, 0))
                        return
                read_future = self.loop.create_future()
                self.loop.add_reader(self._sock_fd, read_future.set_result, None)
                try:
                    await read_future
                finally:
                    self.loop.remove_reader(self._sock_fd)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.closed:
                try:
                    self._receive_queue.put_nowait((e, 0))
                except asyncio.QueueFull:
                    pass
        finally:
            try:
                self._receive_queue.put_nowait(
                    (WebSocketClosed("Connection closed."), 0)
                )
            except asyncio.QueueFull:
                pass

            if not self.closed:
                self.loop.create_task(self.close(WsCloseCode.ABNORMAL_CLOSURE))

    async def _write_loop(self) -> None:
        """The main asynchronous task for writing outgoing WebSocket frames.

        This method runs a continuous loop that consumes messages from the
        `_send_queue`. To improve performance and reduce system call overhead,
        it implements an adaptive batching strategy. It greedily gathers
        multiple pending messages from the queue and then coalesces the
        payloads of messages that share the same flags (e.g., all text frames)
        into a single, larger payload, ONLY if the attribute to coalesce frames
        is enabled. Otherwise, it will batch as many as possible, then iterate
        over the batch and send the frames, one at a time.

        This batching and coalescing significantly improves throughput for
        high volumes of small messages. The final, consolidated payloads are
        then passed to the `_send_coalesced` method for transmission.
        """
        try:
            while not self.closed:
                try:
                    # Get the first message to start a batch, but with a timeout
                    payload, flags = await asyncio.wait_for(
                        self._send_queue.get(), timeout=self._max_batching_delay
                    )
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    break

                # Create a batch, starting with the first message
                batch = [(payload, flags)]

                # Greedily pull more messages from the queue without waiting
                while (
                    len(batch) < self._max_send_batch_size
                    and not self._send_queue.empty()
                ):
                    try:
                        next_payload, next_flags = self._send_queue.get_nowait()
                        batch.append((next_payload, next_flags))
                    except asyncio.QueueEmpty:
                        break

                # Conditionally process the batch based on the coalescing strategy.
                if self._coalesce_frames:
                    coalesced_payloads: dict[int, list[bytes]] = {}

                    for payload_chunk, frame_flags in batch:
                        # If we haven't seen this flag type yet, create a new list for it.
                        if frame_flags not in coalesced_payloads:
                            coalesced_payloads[frame_flags] = []

                        # Append the current chunk to the list for its flag type.
                        coalesced_payloads[frame_flags].append(payload_chunk)

                    # Now, iterate through the dictionary.
                    for msg_flags, list_of_payloads in coalesced_payloads.items():
                        if list_of_payloads:
                            # Join the list of chunks into a single bytes object.
                            full_payload = b"".join(list_of_payloads)
                            await self._send_coalesced(full_payload, msg_flags)
                else:
                    # Safe and preserves frame boundaries, the default.
                    for msg_payload, msg_flags in batch:
                        if msg_payload:
                            await self._send_coalesced(msg_payload, msg_flags)

                # Mark all tasks in the processed batch as done
                for _ in range(len(batch)):
                    self._send_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.closed:
                await self._receive_queue.put((e, 0))
        finally:
            # If the write loop dies, the whole connection is closed.
            if not self.closed:
                self.loop.create_task(self.close(WsCloseCode.ABNORMAL_CLOSURE))

    async def _send_chunk(self, chunk_view: memoryview, flags: CurlWsFlag) -> int:
        """Sends a single chunk of data, handling EAGAIN and write locks.

        This is the lowest-level write operation. It acquires the asyncio Lock
        to ensure that calls to the underlying `curl_ws_send` are serialized,
        making it safe from concurrent access. The lock is held for the
        shortest possible duration. It will wait for the socket to become
        writable if libcurl returns an EAGAIN error.
        """
        while True:
            try:
                async with self._send_lock:
                    return self._curl.ws_send(chunk_view, flags)
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    write_future = self.loop.create_future()
                    self.loop.add_writer(self._sock_fd, write_future.set_result, None)
                    try:
                        await write_future
                    finally:
                        self.loop.remove_writer(self._sock_fd)
                    continue
                raise

    async def _send_coalesced(self, payload: bytes, flags: CurlWsFlag) -> None:
        """Breaks a payload into chunks and sends them sequentially.

        This coroutine is responsible for the fragmentation of a potentially
        large payload into chunks that are suitable for libcurl. It then
        delegates the actual transmission of each chunk, including lock
        acquisition and non-blocking I/O management, to the `_send_chunk`
        method.

        Args:
            payload: The complete byte payload to be sent.
            flags: The CurlWsFlag indicating the frame type (e.g., TEXT, BINARY).
        """
        view = memoryview(payload)
        offset = 0
        write_ops_since_yield = 0

        while offset < len(view):
            chunk_size = min(len(view) - offset, self._MAX_CURL_FRAME_SIZE)
            chunk_view = view[offset : offset + chunk_size]
            if (write_ops_since_yield & self._BATCHING_YIELD_INTERVAL) == 0:
                await asyncio.sleep(0)
                write_ops_since_yield = 0

            try:
                n_sent = await self._send_chunk(chunk_view, flags)
            except CurlError as e:
                await self._receive_queue.put((e, 0))
                return

            offset += n_sent
            write_ops_since_yield += 1

    async def send_from_iterator(
        self, data_iterator: Union[Iterable[bytes], AsyncIterable[bytes]]
    ) -> None:
        """
        Specialized send method to provide the highest possible transfer rate,
        best for maximum throughput of bulk data streams (e.g. file transfers, video).
        It uses a direct, queue-less path to send the frame with the least possible
        overhead. This should not be called at the same time as a regular `send()`,
        concurrent sending is not supported, locking means only one sender runs.

        Warning: The lock is held until the iterator is exhausted. If the iterator
        is slow, this will block the `send()` functionality until it finishes.

        Args:
            data_iterator (Union[Iterable[bytes], AsyncIterable[bytes]]):
            Iterable to stream the data from.

        Raises:
            WebSocketClosed: The WebSocket is closed.
        """
        if self.closed:
            raise WebSocketClosed("WebSocket is closed")
        self._start_io_tasks()
        if hasattr(data_iterator, "__aiter__"):
            iterator = data_iterator.__aiter__()
            get_next = iterator.__anext__
            is_async = True
        else:
            iterator = iter(data_iterator)
            get_next = iterator.__next__
            is_async = False
        view = None
        offset = 0
        write_ops_since_yield = 0

        async with self._send_lock:
            while True:
                if view is None or offset >= len(view):
                    try:
                        chunk = await get_next() if is_async else get_next()
                        view = memoryview(chunk)
                        offset = 0
                    except (StopIteration, StopAsyncIteration):
                        break

                chunk_size = min(len(view) - offset, self._MAX_CURL_FRAME_SIZE)
                chunk_view = view[offset : offset + chunk_size]

                if (write_ops_since_yield & self._BATCHING_YIELD_INTERVAL) == 0:
                    await asyncio.sleep(0)
                    write_ops_since_yield = 0

                try:
                    while True:
                        try:
                            n_sent = self._curl.ws_send(chunk_view, CurlWsFlag.BINARY)
                            break
                        except CurlError as e:
                            if e.code == CurlECode.AGAIN:
                                write_future = self.loop.create_future()
                                self.loop.add_writer(
                                    self._sock_fd, write_future.set_result, None
                                )
                                try:
                                    await write_future
                                finally:
                                    self.loop.remove_writer(self._sock_fd)
                                continue
                            raise
                except CurlError as e:
                    await self._receive_queue.put((e, 0))
                    return

                offset += n_sent
                write_ops_since_yield += 1

    async def flush(self) -> None:
        """
        Waits until the send queue is empty.

        This ensures that all messages passed to `send()` have been picked up
        by the internal writer task. It does not guarantee that the data has
        been written to the OS socket buffer or sent over the network.
        """
        await self._send_queue.join()

    def _handle_close_frame(self, message: bytes) -> None:
        """Unpack and handle the closing frame."""
        try:
            self._close_code, self._close_reason = self._unpack_close_frame(message)
        except WebSocketError as e:
            self._close_code = e.code
        finally:
            if self.autoclose and not self.closed:
                self.loop.create_task(self.close(self._close_code or WsCloseCode.OK))
