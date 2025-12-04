from __future__ import annotations

import asyncio
import struct
import threading
import warnings
from collections.abc import Callable
from contextlib import suppress
from enum import IntEnum
from functools import partial
from json import dumps, loads
from select import select
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Optional, TypeVar, Union

from ..aio import CURL_SOCKET_BAD, get_selector
from ..const import CurlECode, CurlInfo, CurlOpt, CurlWsFlag
from ..curl import Curl, CurlError
from ..utils import CurlCffiWarning
from .exceptions import SessionClosed, Timeout
from .models import Response
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
    RECV_QUEUE_ITEM = tuple[Union[bytes, Exception], int]
    SEND_QUEUE_ITEM = tuple[bytes, Union[CurlWsFlag, int]]


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
    __slots__ = (
        "_curl",
        "autoclose",
        "_close_code",
        "_close_reason",
        "debug",
        "closed",
    )

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
                if code == WsCloseCode.UNKNOWN or code < 1000 or code >= 5000:
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

    __slots__ = (
        "skip_utf8_validation",
        "_emitters",
        "keep_running",
    )

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
        self.keep_running = False

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
    An asyncio WebSocket implementation using libcurl.

    NOTE: This object represents a single WebSocket connection. Once closed,
    it cannot be reopened. A new instance must be created to reconnect.
    """

    __slots__ = (
        "session",
        "_loop",
        "_sock_fd",
        "_close_lock",
        "_terminate_lock",
        "_read_task",
        "_write_task",
        "_close_handle",
        "_receive_queue",
        "_send_queue",
        "_max_send_batch_size",
        "_coalesce_frames",
        "retry_on_recv_error",
        "_yield_interval",
        "_use_fair_scheduling",
        "_yield_mask",
        "_recv_error_retries",
        "_terminated",
        "_terminated_event",
    )

    # Match libcurl's documented max frame size limit.
    _MAX_CURL_FRAME_SIZE: ClassVar[int] = 65535
    _MAX_RECV_RETRIES: ClassVar[int] = 3
    _RECV_RETRY_DELAY: ClassVar[float] = 0.3

    def __init__(
        self,
        session: AsyncSession,
        curl: Curl,
        *,
        autoclose: bool = True,
        debug: bool = False,
        recv_queue_size: int = 512,
        send_queue_size: int = 256,
        max_send_batch_size: int = 256,
        coalesce_frames: bool = False,
        retry_on_recv_error: bool = False,
        yield_interval: float = 0.001,
        fair_scheduling: bool = False,
        yield_mask: int = 63,
    ) -> None:
        """Initializes an Async WebSocket session.

        This class should not be instantiated directly. It is intended to be created
        via the `AsyncSession.ws_connect()` method, which correctly handles setup and
        initialization of the underlying I/O tasks.

        Important:
            This WebSocket implementation uses a decoupled I/O model. Network
            operations occur in background tasks. As a result, network-related
            errors that occur during a `send()` operation will not be raised by
            `send()`. Instead, they are placed into the receive queue and will be
            raised by the next call to `recv()`.

        Args:
            session (AsyncSession): An instantiated AsyncSession object.
            curl (Curl): The underlying Curl to use.
            autoclose (bool, optional): Close the WS on receiving a close frame.
            debug (bool, optional): Enable debug messages. Defaults to False.
            recv_queue_size (int, optional): The maximum number of incoming WebSocket
                messages to buffer internally. This queue stores messages received
                by the Curl socket that are waiting to be consumed by calling `recv()`
            send_queue_size (int, optional): The maximum number of outgoing WebSocket
                messages to buffer before applying network backpressure. When you call
                `send(...)` the message is placed in this queue and transmitted when
                the Curl socket is next available for sending.
            max_send_batch_size (int, optional): The max number of messages per batch.
            coalesce_frames (bool, optional): Combine multiple frames into a batch.
            retry_on_recv_error (bool, optional): Retry recv on some transient errors.
            yield_interval (float, optional): How often to yield control in seconds.
            fair_scheduling (bool, optional): Change the ~5:1 ratio in favor
                of `recv`:`send` to a fairer 1:1 ratio. This decreases recv throughput.
            yield_mask (int, optional): A bitmask that sets the yield frequency for
                cooperative multitasking, checked every `yield_mask + 1` operations.
                Must be a power of two minus one (e.g., `63`, `127`, `255`) for
                efficient bitwise checks. Lower values increase fairness; higher values
                increase throughput.
        """
        super().__init__(curl=curl, autoclose=autoclose, debug=debug)
        self.session: AsyncSession[Response] = session
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._sock_fd: int = -1
        self._close_lock: asyncio.Lock = asyncio.Lock()
        self._terminate_lock: threading.Lock = threading.Lock()
        self._terminated_event: asyncio.Event = asyncio.Event()
        self._read_task: Optional[asyncio.Task[None]] = None
        self._write_task: Optional[asyncio.Task[None]] = None
        self._close_handle: Optional[asyncio.Handle] = None
        self._receive_queue: asyncio.Queue[RECV_QUEUE_ITEM] = asyncio.Queue(
            maxsize=recv_queue_size
        )
        self._send_queue: asyncio.Queue[SEND_QUEUE_ITEM] = asyncio.Queue(
            maxsize=send_queue_size
        )
        self._max_send_batch_size: int = max_send_batch_size
        self._coalesce_frames: bool = coalesce_frames
        self.retry_on_recv_error: bool = retry_on_recv_error
        self._yield_interval: float = yield_interval
        self._use_fair_scheduling: bool = fair_scheduling
        self._yield_mask: int = yield_mask
        self._recv_error_retries: int = 0
        self._terminated: bool = False

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        """Get a reference to the running event loop"""
        if self._loop is None:
            self._loop = get_selector(asyncio.get_running_loop())
        return self._loop

    @property
    def send_queue_size(self) -> int:
        """Returns the current number of items in the send queue."""
        return self._send_queue.qsize()

    def is_alive(self) -> bool:
        """
        Checks if the background I/O tasks are still running.

        Returns `False` if either the read or write task has terminated due
        to an error or a clean shutdown.

        Note: This is a snapshot in time. A return value of `True` does not
        guarantee the next network operation will succeed, but `False`
        definitively indicates the connection is no longer active.
        """
        if self.closed or self._terminated:
            return False

        if self._read_task and self._read_task.done():
            return False

        return not (self._write_task and self._write_task.done())

    def __del__(self) -> None:
        """Warn if the user forgets to close the connection."""

        if getattr(self, "closed", True):
            return

        with suppress(Exception):
            warnings.warn(
                f"Unclosed WebSocket {self!r} was garbage collected. "
                "Always call await ws.close() to ensure clean shutdown.",
                ResourceWarning,
                stacklevel=2,
            )

    def __aiter__(self) -> Self:
        if self.closed:
            raise WebSocketClosed("WebSocket has been closed")
        return self

    async def __anext__(self) -> bytes:
        msg, flags = await self.recv()
        if (msg is None) or (flags & CurlWsFlag.CLOSE):
            raise StopAsyncIteration
        return msg

    def _start_io_tasks(self) -> None:
        """Start the read/write I/O loop tasks.
        This should be called only once after object creation by the factory.
        Once started, the tasks cannot be restarted again, this is a one-shot.

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

        # Get an identifier for the websocket from its object id
        ws_id: str = f"WebSocket-{id(self):#x}"

        # Start the I/O loop tasks
        self._read_task = self.loop.create_task(self._read_loop(), name=f"{ws_id}-read")
        self._write_task = self.loop.create_task(
            self._write_loop(), name=f"{ws_id}-write"
        )

    async def recv(
        self, *, timeout: Optional[float] = None
    ) -> tuple[Optional[bytes], int]:
        """Receive a frame as bytes.

        This method waits for and returns the next complete data frame from the
        receive queue.

        Args:
            timeout: how many seconds to wait before giving up.

        Raises:
            WebSocketClosed: If `recv()` is called on a closed connection after
                the receive queue is empty.
            WebSocketTimeout: If the operation times out.
            WebSocketError: A protocol or network error that occurred in a
                background I/O task, including errors from previous `send()`
                operations.

        Returns:
            tuple[bytes, int]: A tuple with the received payload and flags.
        """
        if self.closed and self._receive_queue.empty():
            raise WebSocketClosed("WebSocket is closed")
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
        self,
        payload: Union[str, bytes, bytearray, memoryview],
        flags: CurlWsFlag = CurlWsFlag.BINARY,
    ):
        """Send a data frame.

        This method is a lightweight, non-blocking call that places the payload
        into a send queue. The actual network transmission is handled by a
        background task.

        To guarantee all your messages have been sent `await ws.flush(...)`.

        The max frame size supported by libcurl is `65535` bytes. Larger frames
        will be broken down and sent in chunks of that size.

        Args:
            payload: data to send.
            flags: flags for the frame.

        Raises:
            WebSocketClosed: The WebSocket is closed.

        NOTE:
            Due to the asynchronous nature of this client, network errors
            (e.g., connection dropped) that occur during the actual transmission
            will NOT be raised by this method. They will be raised by a
            subsequent call to `recv()`. Always ensure you are actively
            receiving data to handle potential connection errors.

            Also: If the network is slow and the internal send queue becomes full,
            this method will block until there is space in the queue.
        """

        if self.closed:
            raise WebSocketClosed("WebSocket is closed")

        # cURL expects bytes
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        elif isinstance(payload, (bytearray, memoryview)):
            payload = bytes(payload)

        try:
            self._send_queue.put_nowait((payload, flags))
        except asyncio.QueueFull:
            await self._send_queue.put((payload, flags))

    async def send_binary(self, payload: bytes) -> None:
        """Send a binary frame.

        Args:
            payload: binary data to send.

        For more info, see the docstring for `send(...)`
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_bytes(self, payload: bytes) -> None:
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: binary data to send.

        For more info, see the docstring for `send(...)`
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_str(self, payload: str) -> None:
        """Send a text frame.

        Args:
            payload: text data to send.

        For more info, see the docstring for `send(...)`
        """
        return await self.send(payload, CurlWsFlag.TEXT)

    async def send_json(
        self, payload: Any, *, dumps: Callable[[Any], str] = dumps
    ) -> None:
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is `json.dumps(...)`.

        For more info, see the docstring for `send(...)`
        """
        return await self.send_str(dumps(payload))

    async def ping(self, payload: Union[str, bytes]):
        """Send a ping frame.

        Args:
            payload: data to send.

        For more info, see the docstring for `send(...)`
        """
        return await self.send(payload, CurlWsFlag.PING)

    async def close(
        self, code: int = WsCloseCode.OK, message: bytes = b"", timeout: float = 5.0
    ) -> None:
        """
        Performs a graceful WebSocket closing handshake and terminates the connection.

        This method sends a WebSocket close frame to the peer, waits for queued
        outgoing messages to be sent, and then shuts down the connection. This is
        the recommended way to close the session.

        Args:
            code (int, optional): Close code. Defaults to `WsCloseCode.OK`.
            message (bytes, optional): Close reason. Defaults to `b""`.
            timeout (float, optional): How long in seconds to wait closed.
        """
        async with self._close_lock:
            if self.closed:
                return

            self.closed = True

            try:
                if self._write_task and not self._write_task.done():
                    close_frame = self._pack_close_frame(code, message)
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            self._send_queue.put((close_frame, CurlWsFlag.CLOSE)),
                            timeout=timeout,
                        )
                    with suppress(WebSocketTimeout, WebSocketError):
                        await self.flush(timeout)

            finally:
                self.terminate()

                # Wait for the termination completion signal
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._terminated_event.wait(), timeout)

    def terminate(self) -> None:
        """
        Immediately terminates the connection without a graceful handshake.

        This method is a forceful shutdown that cancels all background I/O tasks
        and cleans up resources. It should be used for final cleanup or after an
        unrecoverable error. Unlike `close()`, it does not attempt to send a close
        frame or wait for pending messages. It schedules the cleanup to run on the
        event loop and returns immediately. It does not wait for cleanup completion.

        This method is thread-safe, task-safe, and idempotent.
        """

        with self._terminate_lock:
            if self._terminated:
                return
            self._terminated = True

            # Terminate the connection in a thread-safe way
            if self._loop and self.loop.is_running():
                self._close_handle = self.loop.call_soon_threadsafe(
                    lambda: self.loop.create_task(self._terminate_helper())
                )

            # The event loop is not running
            else:
                super().terminate()
                if self.session and not self.session._closed:
                    # WebSocket curls CANNOT be reused
                    self.session.push_curl(None)
                    self._terminated_event.set()

    async def _read_loop(self) -> None:
        """The main asynchronous task for reading incoming WebSocket frames.

        This method is fully event-driven. It waits for the underlying socket
        to become readable, and upon being woken by the event loop, it drains
        all buffered data from libcurl until it receives an EAGAIN error. This
        error signals that the buffer is empty, and the loop returns to an
        idle state, waiting for the next readability event.

        To ensure cooperative multitasking during high-volume message streams,
        the loop yields control to the asyncio event loop periodically.

        If the receive queue becomes full, await `self._receive_queue.put(...)`
        will block the reader loop and stall the socket read task. Thus, appropriate
        queue sizes should be set by the user, even though the defaults are generous
        and should be suitable for most use cases.
        """

        # Cache locals to avoid repeated attribute lookups
        curl_ws_recv = self._curl.ws_recv
        queue_put_nowait = self._receive_queue.put_nowait
        queue_put = self._receive_queue.put
        loop = self.loop
        fair_scheduling = self._use_fair_scheduling
        yield_mask = self._yield_mask
        yield_interval = self._yield_interval

        chunks: list[bytes] = []
        msg_counter = 0
        try:
            # The outer loop waits for readability events.
            while not self.closed:
                # Wait for the socket to be readable.
                read_future = loop.create_future()

                try:
                    loop.add_reader(self._sock_fd, read_future.set_result, None)
                except Exception as exc:
                    with suppress(asyncio.QueueFull):
                        queue_put_nowait(
                            (
                                WebSocketError(
                                    f"add_reader failed: {exc}",
                                    CurlECode.NO_CONNECTION_AVAILABLE,
                                ),
                                0,
                            )
                        )
                    self.terminate()
                    return

                try:
                    await read_future
                finally:
                    # Remove the reader immediately after waking.
                    if self._sock_fd != -1:
                        loop.remove_reader(self._sock_fd)

                # There is data, so we now read until it's empty.
                start_time = loop.time()
                while True:
                    try:
                        chunk, frame = curl_ws_recv()
                        flags: int = frame.flags
                        if self._recv_error_retries > 0:
                            self._recv_error_retries = 0

                        # If a CLOSE frame is received, the reader is done.
                        if flags & CurlWsFlag.CLOSE:
                            with suppress(asyncio.QueueFull):
                                queue_put_nowait((chunk, flags))
                            await self._handle_close_frame(chunk)
                            return

                        # Collect the chunk
                        chunks.append(chunk)

                        # If the message is complete, process and dispatch it
                        if frame.bytesleft <= 0 and (flags & CurlWsFlag.CONT) == 0:
                            message = b"".join(chunks)
                            chunks.clear()
                            try:
                                queue_put_nowait((message, flags))
                            except asyncio.QueueFull:
                                await queue_put((message, flags))

                        msg_counter += 1
                        op_check: bool = (msg_counter & yield_mask) == 0
                        time_check: bool = loop.time() - start_time > yield_interval

                        if (
                            (op_check or time_check)
                            if fair_scheduling
                            else (op_check and time_check)
                        ):
                            await asyncio.sleep(0)
                            start_time = loop.time()

                    except CurlError as e:
                        # Normal EAGAIN from Curl
                        if e.code == CurlECode.AGAIN:
                            break

                        # Transient error, can be retried
                        if (
                            e.code == CurlECode.RECV_ERROR
                            and self.retry_on_recv_error
                            and self._recv_error_retries < self._MAX_RECV_RETRIES
                        ):
                            self._recv_error_retries += 1
                            await asyncio.sleep(
                                self._RECV_RETRY_DELAY * self._recv_error_retries
                            )
                            continue

                        # Unrecoverable, place error on queue and cleanup
                        with suppress(asyncio.QueueFull):
                            queue_put_nowait((e, 0))
                        self.terminate()
                        return

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.closed:
                with suppress(asyncio.QueueFull):
                    queue_put_nowait((e, 0))
            self.terminate()
        finally:
            with suppress(asyncio.QueueFull):
                queue_put_nowait((WebSocketClosed("Connection closed."), 0))

    async def _write_loop(self) -> None:
        """
        The high-level send manager. It efficiently gathers pending messages
        from the send queue and orchestrates their transmission.

        This method runs a continuous loop that consumes messages from the
        `_send_queue`. To improve performance and reduce system call overhead,
        it implements an adaptive batching strategy. It greedily gathers
        multiple pending messages from the queue and then coalesces the
        payloads of messages that share the same flags (e.g., all text frames)
        into a single, larger payload, ONLY if `coalesce_frames=True` and the
        frame is not a CONTROL frame, as the spec requires them to be whole.

        It will batch as many as possible, then iterate over the batch and send
        the frames, one at a time. This batching and coalescing significantly
        improves throughput for high volumes of small messages where the message
        boundaries do not matter. The final, consolidated payloads are then passed
        to the `_send_payload` method for transmission.
        """
        control_frame_flags: int = CurlWsFlag.CLOSE | CurlWsFlag.PING
        send_payload = self._send_payload
        queue_get = self._send_queue.get
        queue_get_nowait = self._send_queue.get_nowait

        try:
            while True:
                payload, flags = await queue_get()

                # Build the rest of the batch without awaiting.
                batch = [(payload, flags)]
                if not flags & CurlWsFlag.CLOSE:
                    while len(batch) < self._max_send_batch_size:
                        try:
                            payload, frame = queue_get_nowait()
                            batch.append((payload, frame))
                            if frame & CurlWsFlag.CLOSE:
                                break

                        except asyncio.QueueEmpty:
                            break

                try:
                    # Process the batch depending on the coalescing strategy
                    if self._coalesce_frames:
                        data_to_coalesce: dict[int, list[bytes]] = {}
                        for payload, frame in batch:
                            if frame & control_frame_flags:
                                # Flush any pending data before the control frame.
                                for frame_group, payloads in data_to_coalesce.items():
                                    if not await send_payload(
                                        b"".join(payloads), frame_group
                                    ):
                                        return
                                data_to_coalesce.clear()

                                if not await send_payload(payload, frame):
                                    return
                            else:
                                data_to_coalesce.setdefault(frame, []).append(payload)

                        # Send any remaining data at the end of the batch.
                        for frame_group, payloads in data_to_coalesce.items():
                            if not await send_payload(b"".join(payloads), frame_group):
                                return
                    else:
                        # Send each message in the batch, preserving frame boundaries.
                        for payload, frame in batch:
                            if not await send_payload(payload, frame):
                                return

                finally:
                    # Mark all processed items as done.
                    for _ in range(len(batch)):
                        self._send_queue.task_done()

                # Exit cleanly after sending a CLOSE frame.
                if batch[-1][1] & CurlWsFlag.CLOSE:
                    break

        except asyncio.CancelledError:
            pass

        except Exception as e:
            if not self.closed:
                with suppress(asyncio.QueueFull):
                    self._receive_queue.put_nowait((e, 0))

        finally:
            # If the loop exits unexpectedly, ensure we terminate the connection.
            if not self.closed:
                self.terminate()

    async def _send_payload(self, payload: bytes, flags: CurlWsFlag) -> bool:
        """
        The low-level I/O Handler. It transmits a single payload, handling
        fragmentation, backpressure (EAGAIN), and cooperative multitasking.
        Returns False on a non-recoverable error.

        Args:
            payload: The complete byte payload to be sent.
            flags: The `CurlWsFlag` indicating the frame type (e.g., `TEXT`, `BINARY`).
        """

        # Cache locals to reduce lookup cost
        curl_ws_send = self._curl.ws_send
        queue_put_nowait = self._receive_queue.put_nowait
        loop = self.loop

        view = memoryview(payload)
        offset = 0
        write_ops = 0
        start_time: float = loop.time()

        while offset < len(view):
            # Cooperatively yield to the event loop to prevent starvation.
            if (write_ops & self._yield_mask) == 0 or (
                loop.time() - start_time
            ) > self._yield_interval:
                await asyncio.sleep(0)
                start_time = loop.time()

            try:
                chunk = view[offset : offset + self._MAX_CURL_FRAME_SIZE]
                n_sent = curl_ws_send(chunk, flags)
                if n_sent == 0:
                    with suppress(asyncio.QueueFull):
                        queue_put_nowait(
                            (
                                WebSocketError(
                                    "ws_send returned 0 bytes",
                                    CurlECode.SEND_ERROR,
                                ),
                                0,
                            )
                        )
                    return False
                offset += n_sent
                write_ops += 1

            except CurlError as e:
                if e.code != CurlECode.AGAIN:
                    # Non-recoverable error: queue it for the user and signal failure.
                    with suppress(asyncio.QueueFull):
                        queue_put_nowait((e, 0))
                    return False

                # EAGAIN: wait until the socket is writable.
                write_future = loop.create_future()

                try:
                    loop.add_writer(self._sock_fd, write_future.set_result, None)
                except Exception as exc:
                    with suppress(asyncio.QueueFull):
                        queue_put_nowait(
                            (
                                WebSocketError(
                                    f"add_writer failed: {exc}",
                                    CurlECode.NO_CONNECTION_AVAILABLE,
                                ),
                                0,
                            )
                        )
                    return False

                try:
                    await write_future
                finally:
                    if self._sock_fd != -1:
                        loop.remove_writer(self._sock_fd)
        return True

    async def flush(self, timeout: Optional[float] = None) -> None:
        """Waits until all items in the send queue have been processed.

        This ensures that all messages passed to `send()` have been handed off to the
        underlying socket for transmission. It does not guarantee that the data has
        been received by the remote peer.

        Args:
            timeout (Optional[float], optional): The maximum number of seconds to wait
            for the queue to drain.

        Raises:
            WebSocketTimeout:  If the send queue is not fully processed within the
            specified ``timeout`` period.
            WebSocketError: If the writer task has already terminated while unsent
            messages remain in the queue.
        """
        if (
            self._write_task
            and self._write_task.done()
            and not self._send_queue.empty()
        ):
            raise WebSocketError(
                "Cannot flush, writer task has terminated unexpectedly."
            )

        try:
            await asyncio.wait_for(self._send_queue.join(), timeout=timeout)
        except asyncio.TimeoutError as e:
            raise WebSocketTimeout("Timed out waiting for send queue to flush.") from e

    async def _terminate_helper(self) -> None:
        """Utility method for connection termination"""
        tasks_to_cancel: set[asyncio.Task[None]] = set()
        max_timeout: int = 3

        try:
            # Cancel all the I/O tasks
            for io_task in (self._read_task, self._write_task):
                try:
                    if io_task and not io_task.done():
                        io_task.cancel()
                        tasks_to_cancel.add(io_task)
                except (asyncio.CancelledError, RuntimeError):
                    ...

            # Wait for cancellation but don't get stuck
            if tasks_to_cancel:
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        asyncio.gather(*tasks_to_cancel, return_exceptions=True),
                        timeout=max_timeout,
                    )

            # Drain the send_queue
            while not self._send_queue.empty():
                try:
                    self._send_queue.get_nowait()
                    self._send_queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    break

            # Remove the reader/writer if still registered
            if self._sock_fd != -1:
                with suppress(Exception):
                    self.loop.remove_reader(self._sock_fd)
                with suppress(Exception):
                    self.loop.remove_writer(self._sock_fd)

            self._sock_fd = -1

            # Close the Curl connection
            super().terminate()
            if self.session and not self.session._closed:
                # WebSocket curls CANNOT be reused
                self.session.push_curl(None)

        finally:
            self._terminated_event.set()

    async def _handle_close_frame(self, message: bytes) -> None:
        """Unpack and handle the closing frame, then initiate shutdown."""
        try:
            self._close_code, self._close_reason = self._unpack_close_frame(message)
        except WebSocketError as e:
            self._close_code = e.code

        if self.autoclose and not self.closed:
            await self.close(self._close_code or WsCloseCode.OK)
        else:
            # If not sending a reply, we must still terminate the connection.
            self.terminate()
