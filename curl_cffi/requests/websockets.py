"""
The Curl CFFI WebSocket client implementation.
"""

from __future__ import annotations

import asyncio
import struct
import threading
import warnings
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from enum import IntEnum
from functools import partial
from json import dumps as json_dumps
from json import loads as json_loads
from random import uniform
from select import select
from typing import TYPE_CHECKING, ClassVar, Literal, TypeVar, cast

from ..aio import CURL_SOCKET_BAD, get_selector
from ..const import CurlECode, CurlInfo, CurlOpt, CurlWsFlag
from ..curl import Curl, CurlError
from ..utils import CurlCffiWarning
from .exceptions import SessionClosed, Timeout
from .models import Response
from .utils import NOT_SET, NotSetType, set_curl_options

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
    ON_MESSAGE_T = Callable[["WebSocket", bytes | str], None]
    ON_ERROR_T = Callable[["WebSocket", CurlError], None]
    ON_OPEN_T = Callable[["WebSocket"], None]
    ON_CLOSE_T = Callable[["WebSocket", int, str], None]
    RECV_QUEUE_ITEM = tuple[bytes, int]
    SEND_QUEUE_ITEM = tuple[bytes, CurlWsFlag]


# We need a partial for dumps() because a custom function may not accept the parameter
dumps_partial: partial[str] = partial[str](json_dumps, separators=(",", ":"))


@dataclass
class WsRetryOnRecvError:
    """Configurable WebSocket behaviour for retrying failed message receives.

    When enabled, each failed receive attempt will use exponential backoff with
    jitter, calculated as the ``base * (2 ** (attempt - 1)) +- jitter``, where
    the jitter is ``+-10%`` the result of computed delay value.

    retry_on_error: When a WebSocket receive operation fails due to an error,
    retry the receive attempt (``True``) or fail the connection (``False``).
    retry_delay_base: The base value (in seconds) to compute the retry delay from.
    max_retry_count: How many times to retry a receive operation before giving up.
    retry_error_codes: Set of ``CurlECode`` values for which the receive operation
    should be retried. Default is ``CurlECode.RECV_ERROR``.
    """

    retry_on_error: bool = False
    retry_delay_base: float = 0.3
    max_retry_count: int = 3
    retry_error_codes: set[CurlECode] = field(
        default_factory=lambda: {CurlECode.RECV_ERROR}
    )


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
        self, message: str, code: WsCloseCode | CurlECode | Literal[0] = 0
    ) -> None:
        super().__init__(message, code)  # type: ignore


class WebSocketClosed(  # pyright: ignore[reportUnsafeMultipleInheritance]
    WebSocketError, SessionClosed
):
    """WebSocket is already closed."""


class WebSocketTimeout(  # pyright: ignore[reportUnsafeMultipleInheritance]
    WebSocketError, Timeout
):
    """WebSocket operation timed out."""


class BaseWebSocket:
    __slots__: tuple[str, ...] = (
        "_curl",
        "autoclose",
        "_close_code",
        "_close_reason",
        "debug",
        "closed",
    )

    def __init__(
        self, curl: Curl | NotSetType, *, autoclose: bool = True, debug: bool = False
    ) -> None:
        self._curl: Curl | NotSetType = curl
        self.autoclose: bool = autoclose
        self._close_code: int | None = None
        self._close_reason: str | None = None
        self.debug: bool = debug
        self.closed: bool = False

    @property
    def curl(self) -> Curl:
        """Return reference to Curl associated with current WebSocket."""
        if isinstance(self._curl, NotSetType):
            self._curl = Curl(debug=self.debug)
        return self._curl

    @property
    def close_code(self) -> int | None:
        """The WebSocket close code, if the connection has been closed."""
        return self._close_code

    @property
    def close_reason(self) -> str | None:
        """The WebSocket close reason, if the connection has been closed."""
        return self._close_reason

    @staticmethod
    def _pack_close_frame(code: int, reason: bytes) -> bytes:
        return struct.pack("!H", code) + reason

    @staticmethod
    def _unpack_close_frame(frame: bytes) -> tuple[int, str]:
        if len(frame) < 2:
            code: int = WsCloseCode.UNKNOWN
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

            if code == WsCloseCode.UNKNOWN or code < 1000 or code >= 5000:
                raise WebSocketError(
                    f"Invalid close code: {code}", WsCloseCode.PROTOCOL_ERROR
                )

        return code, reason

    def terminate(self) -> None:
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
        curl: Curl | NotSetType = NOT_SET,
        *,
        autoclose: bool = True,
        skip_utf8_validation: bool = False,
        debug: bool = False,
        on_open: ON_OPEN_T | None = None,
        on_close: ON_CLOSE_T | None = None,
        on_data: ON_DATA_T | None = None,
        on_message: ON_MESSAGE_T | None = None,
        on_error: ON_ERROR_T | None = None,
    ) -> None:
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
        self.skip_utf8_validation: bool = skip_utf8_validation
        self.keep_running: bool = False

        self._emitters: dict[EventTypeLiteral, Callable[..., object]] = {}
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

    def _emit(
        self,
        event_type: EventTypeLiteral,
        *args: str | bytes | int | CurlWsFrame | CurlError,
    ) -> None:
        callback: Callable[..., object] | None = self._emitters.get(event_type)
        if callback:
            try:
                _ = callback(self, *args)

            # pylint: disable-next=broad-exception-caught
            except Exception as e:
                error_callback: Callable[..., object] | None = self._emitters.get(
                    "error"
                )
                if error_callback:
                    _ = error_callback(self, e)
                else:
                    warnings.warn(
                        f"WebSocket callback '{event_type}' failed",
                        CurlCffiWarning,
                        stacklevel=2,
                    )

    def connect(
        self,
        url: str,
        params: (
            dict[str, object]
            | list[object]
            | tuple[str, int | list[str] | dict[str, str | int]]
            | None
        ) = None,
        headers: HeaderTypes | None = None,
        cookies: CookieTypes | None = None,
        auth: tuple[str, str] | None = None,
        timeout: float | tuple[float, float] | object | None = NOT_SET,
        allow_redirects: bool = True,
        max_redirects: int = 30,
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
        default_headers: bool = True,
        quote: str | Literal[False] = "",
        http_version: CurlHttpVersion | None = None,
        interface: str | None = None,
        cert: str | tuple[str, str] | None = None,
        max_recv_speed: int = 0,
        curl_options: dict[CurlOpt, str] | None = None,
    ) -> Self:
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

        curl: Curl = self.curl
        _ = set_curl_options(
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
        _ = curl.setopt(CurlOpt.CONNECT_ONLY, 2)
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
        chunks: list[bytes] = []
        flags: int = 0

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
        return data.decode("utf-8")

    def recv_json(self, *, loads: Callable[[str], T] = json_loads) -> T:
        """Receive a JSON frame.

        Args:
            loads: JSON decoder, default is json.loads.
        """
        data = self.recv_str()
        return loads(data)

    def send(
        self,
        payload: str | bytes,
        flags: CurlWsFlag = CurlWsFlag.BINARY,
    ) -> int:
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

    def send_binary(self, payload: bytes) -> int:
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

    def send_str(self, payload: str) -> int:
        """Send a text frame.

        Args:
            payload: text data to send.
        """
        return self.send(payload, CurlWsFlag.TEXT)

    def send_json(
        self, payload: object, *, dumps: Callable[..., str] = dumps_partial
    ) -> int:
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is json.dumps.
        """
        return self.send_str(dumps(payload))

    def ping(self, payload: str | bytes) -> int:
        """Send a ping frame.

        Args:
            payload: data to send.
        """
        return self.send(payload, CurlWsFlag.PING)

    def run_forever(self, url: str = "", **kwargs) -> None:
        """Run the WebSocket forever. See :meth:`connect` for details on parameters.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html
        """

        if url:
            _ = self.connect(url, **kwargs)

        sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE
            )

        self._emit("open")

        # Keep reading the messages and invoke callbacks
        # TODO: Reconnect logic
        chunks: list[bytes] = []
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
                        code: int = WsCloseCode.UNKNOWN
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

        # TODO: As per spec, we should wait for the server to close the connection
        # But this is not a requirement
        msg = self._pack_close_frame(code, message)
        _ = self.send(msg, CurlWsFlag.CLOSE)
        # The only way to close the connection appears to be curl_easy_cleanup
        self.terminate()


class AsyncWebSocket(BaseWebSocket):
    """
    An asyncio WebSocket implementation using libcurl.
    """

    __slots__ = (
        "session",
        "_loop",
        "_sock_fd",
        "_close_lock",
        "_terminate_lock",
        "_read_task",
        "_write_task",
        "_receive_queue",
        "_send_queue",
        "_max_send_batch_size",
        "_coalesce_frames",
        "_recv_yield_mask",
        "_send_yield_mask",
        "_terminated",
        "_terminated_event",
        "ws_retry",
        "_transport_exception",
        "_max_message_size",
        "drain_on_error",
    )

    _MAX_CURL_FRAME_SIZE: ClassVar[int] = 65536

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
        ws_retry: WsRetryOnRecvError | None = None,
        recv_yield_mask: int = 31,
        send_yield_mask: int = 15,
        max_message_size: int = 4 * 1024 * 1024,
        drain_on_error: bool = False,
    ) -> None:
        """Initializes an Async WebSocket session.

        This class should not be instantiated directly. It is intended to be created
        via the ``AsyncSession.ws_connect()`` method, which correctly handles setup and
        initialization of the underlying I/O tasks. This object represents a single
        WebSocket connection. Once closed, it cannot be reopened. A new instance must
        be created to reconnect.

        This class implements the async context manager for lifecycle management,
        so you can use it to close the connection automatically on exit:

        ```python
        session = AsyncSession(...)
        ws = session.ws_connect(...)
        async with ws:
            ...
        ```

        Concise example:

        ```python
        async with (
            AsyncSession(...) as session,
            await session.ws_connect(...) as ws,
        ):
            ...
        ```

        Important:
            This WebSocket implementation uses a decoupled I/O model. Network
            operations occur in background tasks. As a result, network-related
            errors are raised in subsequent calls to ``send()`` or ``recv()``.

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
                ``send()`` the message is placed in this queue and transmitted when
                the Curl socket is next available for sending.
            max_send_batch_size (int, optional): The max number of messages per batch.
            coalesce_frames (bool, optional): Combine multiple frames into a batch.
            ws_retry (WsRetryOnRecvError, optional): Retry on failed message receives.
            recv_yield_mask (int): Set the yield frequency for received messages.
            send_yield_mask (int): Set the yield frequency for sent messages.
            max_message_size (int): The maximum size of a complete received message.
            drain_on_error (bool, optional): If ``True``, when a connection error
            occurs, attempt to consume all the buffered received messages first,
            before raising the error. Otherwise, raise it immediately (default).

            Yield masks are bitmasks that sets the yield frequency for cooperative
            multitasking, checked every ``yield_mask + 1`` operations. This value
            must be a power of two minus one (e.g., ``15``, ``31``, ``63``) in
            order to carry out efficient bitwise checks. Lower values increase
            fairness by taking up less event loop time, while higher values
            increase throughput at the cost of consuming more loop time.

        See also:
            https://curl.se/libcurl/c/curl_ws_recv.html
            https://curl.se/libcurl/c/curl_ws_send.html
        """
        super().__init__(curl=curl, autoclose=autoclose, debug=debug)
        self.session: AsyncSession[Response] = session
        self._loop: asyncio.AbstractEventLoop | None = None
        self._sock_fd: int = -1
        self._terminated: bool = False
        self._close_lock: asyncio.Lock = asyncio.Lock()
        self._terminate_lock: threading.Lock = threading.Lock()
        self._terminated_event: asyncio.Event = asyncio.Event()
        self._read_task: asyncio.Task[None] | None = None
        self._write_task: asyncio.Task[None] | None = None
        self._receive_queue: asyncio.Queue[RECV_QUEUE_ITEM] = asyncio.Queue(
            maxsize=recv_queue_size
        )
        self._send_queue: asyncio.Queue[SEND_QUEUE_ITEM] = asyncio.Queue(
            maxsize=send_queue_size
        )
        self._max_send_batch_size: int = max_send_batch_size
        self._coalesce_frames: bool = coalesce_frames
        self.ws_retry: WsRetryOnRecvError = ws_retry or WsRetryOnRecvError()
        self._recv_yield_mask: int = recv_yield_mask
        self._send_yield_mask: int = send_yield_mask
        self._transport_exception: Exception | None = None
        self._max_message_size: int = max_message_size
        self.drain_on_error: bool = drain_on_error

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

        Returns ``False`` if either the read or write task has terminated due
        to an error or a clean shutdown.

        Note: This is a snapshot in time. A return value of ``True`` does not
        guarantee the next network operation will succeed, but ``False``
        definitively indicates the connection is no longer active.
        """
        if self.closed or self._terminated:
            return False

        if self._read_task and self._read_task.done():
            return False

        return not (self._write_task and self._write_task.done())

    async def __aenter__(self) -> Self:
        """Enable context manager usage for automatic session management and closure.
        This cannot be used to initiate a WebSocket connection, that must be done
        beforehand using the :meth:`AsyncSession.ws_connect()` factory method.

        Returns:
            Self: The instantiated AsyncWebSocket object.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """
        On exiting the context manager, close the WebSocket connection.
        """
        await self.close()

    def __aiter__(self) -> Self:
        if self.closed:
            raise WebSocketClosed("WebSocket has been closed")
        return self

    async def __anext__(self) -> bytes:
        msg, flags = await self.recv()
        if flags & CurlWsFlag.CLOSE:
            raise StopAsyncIteration
        return msg

    def _finalize_connection(self, exc: Exception) -> None:
        """Finalize the connection into a terminal state.

        This method is called for all terminal conditions, including:
        - normal WebSocket closure
        - protocol errors
        - transport errors

        After this method is called, no further messages will be delivered
        and all ``recv()`` calls will fail. ``_finalize_connection()`` is intended
        for event-loop context, but ``terminate()`` is thread-safe.

        Args:
            exc (Exception): The exception object that gets raised. This does not
            have to be an error, enqueuing ``WebSocketClosed`` indicates closure.
        """

        if self.closed or self._transport_exception is not None:
            return

        self._transport_exception = exc
        self.terminate()

    def _start_io_tasks(self) -> None:
        """Start the read/write I/O loop tasks.

        NOTE: This should be called only once after object creation by the factory.
        Once started, the tasks cannot be restarted again, this is a one-shot.

        Raises:
            WebSocketError: The WebSocket FD was invalid.
        """

        # Return early if already started
        if self._read_task is not None:
            return

        # Return early if terminated before start
        if self._terminated:
            raise WebSocketClosed("WebSocket already terminated")

        # Check the yield masks are correctly configured
        if (
            self._recv_yield_mask < 1
            or (self._recv_yield_mask & (self._recv_yield_mask + 1)) != 0
        ):
            raise WebSocketError(
                "recv_yield_mask must be a power of two minus one (e.g. 15, 31,63)",
                code=CurlECode.BAD_FUNCTION_ARGUMENT,
            )
        if (
            self._send_yield_mask < 1
            or (self._send_yield_mask & (self._send_yield_mask + 1)) != 0
        ):
            raise WebSocketError(
                "send_yield_mask must be a power of two minus one (e.g. 7, 15,31)",
                code=CurlECode.BAD_FUNCTION_ARGUMENT,
            )

        # Get the currently active socket FD
        self._sock_fd = cast(int, self.curl.getinfo(CurlInfo.ACTIVESOCKET))
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

    async def recv(self, *, timeout: float | None = None) -> tuple[bytes, int]:
        """Receive a WebSocket message.

        This method waits for and returns the next complete WebSocket message.

        Args:
            timeout: How many seconds to wait for a message before raising
            a timeout error.

        Returns:
            tuple[bytes, int]: A tuple with the received payload and flags.

        Raises:
            WebSocketTimeout: If the timeout expires.
            WebSocketClosed: If the connection is closed.
            WebSocketError: If a network-level transport error occurs.

        Notes:
            ``WebSocketError`` exceptions may have originated from a prior
            ``send()`` or ``recv()`` operation, since all operations
            share the same transport state once a failure occurs.

            This method does not wait for additional messages after a transport
            error is detected. If ``drain_on_error=True`` is set, this method
            will return all messages that are already buffered in the receive
            queue at the time ``recv()`` is called, before raising a connection error.

            Unlike some other WebSocket libraries that panic at the sight of
            concurrent ``recv()`` calls, this method fully supports concurrent
            invocations — each caller awaits the next available message and
            receives distinct messages in FIFO order.
        """
        # Fast-fail when transport already errored and we aren't draining.
        if self._transport_exception is not None and not self.drain_on_error:
            raise self._transport_exception

        # Hot path: immediate buffered item (zero allocation).
        try:
            return self._receive_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass

        # Terminal checks when queue is empty.
        if self._transport_exception is not None:
            raise self._transport_exception

        if self._read_task is None or self._read_task.done():
            raise WebSocketClosed("WebSocket is closed")

        # Cold path: wait for data or for the reader task to finish.
        queue_waiter: asyncio.Task[RECV_QUEUE_ITEM] = asyncio.create_task(
            self._receive_queue.get()
        )

        try:
            # Wait for the first of: queue_waiter or _read_task
            done, _ = await asyncio.wait(
                (queue_waiter, self._read_task),
                return_when=asyncio.FIRST_COMPLETED,
                timeout=timeout,
            )

        except asyncio.CancelledError:
            # Caller cancelled — cancel the waiter and re-raise
            if not queue_waiter.done():
                _ = queue_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await queue_waiter
            raise

        # Timeout occurred and no message
        if not done:
            _ = queue_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await queue_waiter
            raise WebSocketTimeout(
                "WebSocket recv() timed out", CurlECode.OPERATION_TIMEDOUT
            )

        # If queue_waiter completed first, return its result.
        if queue_waiter in done:
            return await queue_waiter

        # Reader task finished first. Cancel the waiter.
        _ = queue_waiter.cancel()
        with suppress(asyncio.CancelledError):
            await queue_waiter

        # Try to return one buffered item when drain is set
        if self.drain_on_error:
            try:
                return self._receive_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        # Propagate any transport exception or raise closed.
        if self._transport_exception is not None:
            raise self._transport_exception

        raise WebSocketClosed("Connection closed")

    async def recv_str(self, *, timeout: float | None = None) -> str:
        """Receive a text frame.

        Args:
            timeout: how many seconds to wait before giving up.
        """
        data, flags = await self.recv(timeout=timeout)
        if not (flags & CurlWsFlag.TEXT):
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
        loads: Callable[[str | bytes], T] = json_loads,
        timeout: float | None = None,
    ) -> T:
        """Receive a JSON frame.

        Args:
            loads: JSON decoder, default is :meth:`json.loads`.
            timeout: how many seconds to wait before giving up.

        Raises:
            WebSocketError: Received frame is invalid or failed to decode JSON.
        """
        data, _ = await self.recv(timeout=timeout)
        if not data:
            raise WebSocketError(
                "Received empty frame, cannot decode JSON", WsCloseCode.INVALID_DATA
            )

        try:
            return loads(data)
        except UnicodeDecodeError as e:
            raise WebSocketError(
                "Invalid UTF-8 in JSON text frame", WsCloseCode.INVALID_DATA
            ) from e
        except Exception as e:
            raise WebSocketError(
                f"Invalid JSON payload: {e}", WsCloseCode.INVALID_DATA
            ) from e

    async def send(
        self,
        payload: str | bytes | bytearray | memoryview,
        flags: CurlWsFlag = CurlWsFlag.BINARY,
        timeout: float | None = None,
    ) -> None:
        """Send a data frame.

        libcurl supports frames up to ``65536`` bytes. Larger payloads are split into
        continuation frames so they arrive as a single logical WebSocket message.

        Args:
            payload: Data to send. ``str`` is encoded as ``UTF-8``;
            ``bytes``, ``bytearray``, and ``memoryview`` are sent as-is.
            flags: Bitmask of frame flags (text/binary). Defaults to
            ``CurlWsFlag.BINARY``.
            timeout: Maximum time in seconds to wait if the send queue is full. If
            ``None`` (default), waits indefinitely until space is available.

        Raises:
            WebSocketClosed: If the connection is closed or terminating.
            WebSocketTimeout: If the send queue is full and ``timeout`` expires.
            WebSocketError: If a network-level transport error occurs.

        Notes:
            This is a lightweight, non-blocking call that queues the payload
            for sending. Actual network transmission is performed by a background
            task. To ensure all queued messages have been handed to libcurl,
            call ``await ws.flush()``. This method does not wait for network
            acknowledgement. Network errors during transmission will be raised
            by the next call to ``recv()`` or ``send()``.

            ``WebSocketError`` exceptions may have originated from a prior
            ``send()`` or ``recv()`` operation, since all operations
            share the same transport state once a failure occurs.
        """
        if self._transport_exception is not None:
            raise self._transport_exception

        if self.closed:
            raise WebSocketClosed("WebSocket is closed")

        # cURL expects bytes
        if isinstance(payload, str):
            payload = payload.encode("utf-8")
        elif isinstance(payload, (bytearray, memoryview)):
            payload = bytes(payload)

        try:
            self._send_queue.put_nowait((payload, flags))
        except asyncio.QueueFull as exc:
            if self._terminated:
                raise WebSocketClosed("WebSocket connection is terminated") from exc

            # Check exception after encoding
            if self._transport_exception is not None:
                raise self._transport_exception from exc

            if timeout is not None:
                try:
                    await asyncio.wait_for(
                        self._send_queue.put((payload, flags)), timeout
                    )
                except asyncio.TimeoutError as e:
                    raise WebSocketTimeout(
                        "Send queue full (network slow) - hit timeout enqueuing message"
                    ) from e
            else:
                await self._send_queue.put((payload, flags))

    async def send_binary(self, payload: bytes) -> None:
        """Send a binary frame.

        Args:
            payload: binary data to send.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_bytes(self, payload: bytes) -> None:
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: binary data to send.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_str(self, payload: str) -> None:
        """Send a text frame.

        Args:
            payload: text data to send.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.TEXT)

    async def send_json(
        self, payload: object, *, dumps: Callable[..., str] = dumps_partial
    ) -> None:
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is :meth:`json.dumps()`.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send_str(dumps(payload))

    async def ping(self, payload: str | bytes) -> None:
        """Send a ping frame.

        Args:
            payload: data to send.

        Raises:
            WebSocketError: The payload length is outside specification.

        For more info, see the docstring for :meth:`send()`
        """

        if isinstance(payload, str):
            payload_bytes = payload.encode("utf-8")
        else:
            payload_bytes = bytes(payload)

        if len(payload_bytes) not in range(0, 126):
            raise WebSocketError(
                f"Ping frame has invalid length: {len(payload_bytes)}",
                CurlECode.TOO_LARGE,
            )

        return await self.send(payload_bytes, CurlWsFlag.PING)

    async def close(
        self, code: int = WsCloseCode.OK, message: bytes = b"", timeout: float = 5.0
    ) -> None:
        """
        Performs a graceful WebSocket closing handshake and terminates the connection.

        This method sends a WebSocket close frame to the peer, waits for queued
        outgoing messages to be sent, and then shuts down the connection. This is
        the recommended way to close the session.

        A graceful close is best-effort and may be skipped if termination occurs.

        Args:
            code (int, optional): Close code. Defaults to ``WsCloseCode.OK``.
            message (bytes, optional): Close reason. Defaults to ``b""``.
            timeout (float, optional): How long in seconds to wait closed.
        """
        async with self._close_lock:
            if self.closed:
                return

            self.closed = True

            try:
                if (
                    self._write_task
                    and not self._write_task.done()
                    and self._transport_exception is None
                ):
                    close_frame: bytes = self._pack_close_frame(code, message)
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
                    _ = await asyncio.wait_for(self._terminated_event.wait(), timeout)

    def terminate(self) -> None:
        """
        Immediately terminates the connection without a graceful handshake.

        This method is a forceful shutdown that cancels all background I/O tasks
        and cleans up resources. It should be used for final cleanup or after an
        unrecoverable error. Unlike ``close()``, it does not attempt to send a close
        frame or wait for pending messages. It schedules the cleanup to run on the
        event loop and returns immediately. It does not wait for cleanup completion.

        This method is thread-safe, task-safe, and idempotent.
        """

        with self._terminate_lock:
            if self._terminated:
                return
            self._terminated = True

            loop: asyncio.AbstractEventLoop | None = self._loop
            try:
                if loop is None:
                    raise RuntimeError("Event loop not available")

                # Scheduling from the same thread
                if loop.is_running() and loop == asyncio.get_running_loop():
                    _ = loop.create_task(self._terminate_helper())

                else:
                    # Cross-thread scheduling
                    _ = asyncio.run_coroutine_threadsafe(self._terminate_helper(), loop)

            except RuntimeError:
                try:
                    super().terminate()
                    if self.session and not self.session._closed:
                        # WebSocket curls CANNOT be reused
                        self.session.push_curl(None)
                finally:
                    self._terminated_event.set()

    async def _read_loop(self) -> None:
        """
        The main asynchronous task for reading incoming WebSocket frames.

        Attempts to read immediately and only registers an event loop reader if
        the socket returns EAGAIN (empty). It waits for the underlying socket to
        become readable, and upon being woken by the event loop, it drains all
        buffered data from libcurl until it receives an EAGAIN error. This error
        signals that the buffer is empty, and the loop returns to an idle state,
        waiting for the next readability event. This is "optimistic reading".

        To ensure cooperative multitasking during high-volume message streams,
        the loop yields control to the asyncio event loop periodically which
        is tracked using an operation counter.

        If the receive queue becomes full, ``await self._receive_queue.put()`` will
        block the reader loop and stall the socket read task. Thus, appropriate queue
        sizes should be set by the user, to match the speed at which they are expected
        to be consumed. If latency is a factor, a smaller queue size should be used.
        Conversely, a larger queue size provides burst message handling capacity.
        """

        # Cache locals to avoid repeated attribute lookups
        curl_ws_recv: Callable[[], tuple[bytes, CurlWsFrame]] = self.curl.ws_recv
        queue_put_nowait: Callable[[RECV_QUEUE_ITEM], None] = (
            self._receive_queue.put_nowait
        )
        queue_put: Callable[[RECV_QUEUE_ITEM], Awaitable[None]] = (
            self._receive_queue.put
        )
        loop: asyncio.AbstractEventLoop = self.loop
        yield_mask: int = self._recv_yield_mask
        ws_retry: WsRetryOnRecvError = self.ws_retry
        retry_on_error: bool = ws_retry.retry_on_error
        retry_codes: set[CurlECode] = ws_retry.retry_error_codes
        max_retries: int = ws_retry.max_retry_count
        retry_base: float = float(ws_retry.retry_delay_base)
        e_again: CurlECode = CurlECode.AGAIN
        e_recv_err: CurlECode = CurlECode.RECV_ERROR
        e_nothing: CurlECode = CurlECode.GOT_NOTHING
        close_flag = CurlWsFlag.CLOSE
        cont_flag = CurlWsFlag.CONT
        ping_flag = CurlWsFlag.PING
        control_mask: int = ping_flag | close_flag
        max_msg_size: int = self._max_message_size
        errno_11_msgs: tuple[str, ...] = (
            "errno 11",
            "resource temporarily unavailable",
        )

        # Message specific values
        recv_error_retries: int = 0
        chunks: list[bytes] = []
        msg_counter = 0
        current_msg_size: int = 0

        try:
            while not self.closed:
                try:
                    chunk, frame = curl_ws_recv()

                except CurlError as e:
                    should_retry: bool = False

                    # Handle normal cURL EAGAINs
                    if e.code == e_again:
                        should_retry = True

                    # EAGAIN ("errno 11") bubbling up as RECV_ERROR from BoringSSL
                    elif e.code == e_recv_err:
                        err_msg: str = str(e).lower()
                        if any(msg in err_msg for msg in errno_11_msgs):
                            should_retry = True

                    # Handle Server Disconnect (Empty Reply)
                    elif e.code == e_nothing:
                        final_exc: WebSocketClosed = WebSocketClosed(
                            "Connection closed unexpectedly by server (EOF)",
                            WsCloseCode.ABNORMAL_CLOSURE,
                        )
                        final_exc.__cause__ = e
                        final_exc.__suppress_context__ = True
                        self._finalize_connection(final_exc)
                        return

                    if should_retry:
                        read_future: asyncio.Future[None] = loop.create_future()
                        try:
                            loop.add_reader(self._sock_fd, read_future.set_result, None)
                            await read_future

                        # pylint: disable-next=broad-exception-caught
                        except Exception as exc:
                            self._finalize_connection(
                                WebSocketError(
                                    f"Socket closed unexpectedly: {exc}",
                                    CurlECode.NO_CONNECTION_AVAILABLE,
                                )
                            )
                            return

                        finally:
                            if self._sock_fd != -1:
                                with suppress(Exception):
                                    _ = loop.remove_reader(self._sock_fd)

                        # Loop back to the top to try reading again
                        continue

                    # Apply the user-configured retry logic
                    if (
                        retry_on_error
                        and e.code in retry_codes
                        and recv_error_retries < max_retries
                    ):
                        recv_error_retries += 1
                        # Formula: base * (2 ^ (attempt - 1))
                        retry_delay: float = (  # pyright: ignore[reportAny]
                            retry_base * (2 ** (recv_error_retries - 1))
                        )
                        # Add Jitter: +/- 10%
                        jitter: float = retry_delay * 0.1
                        retry_delay += uniform(-jitter, jitter)
                        await asyncio.sleep(max(0.0, retry_delay))
                        continue

                    # Fatal error - can't retry
                    self._finalize_connection(e)
                    return

                flags: int = frame.flags
                current_msg_size += len(chunk)
                if current_msg_size > max_msg_size:
                    chunks.clear()
                    self._finalize_connection(
                        WebSocketError(
                            (
                                f"Message too large: {current_msg_size} bytes "
                                f"(limit {max_msg_size} bytes). "
                                "Consider increasing max_message_size or "
                                "chunking the message."
                            ),
                            CurlECode.TOO_LARGE,
                        )
                    )
                    return

                if recv_error_retries > 0:
                    recv_error_retries = 0

                # Data Frames (Text / Binary / Cont)
                if not (flags & control_mask):
                    # Collect the chunk
                    chunks.append(chunk)

                    # If the message is complete, process and dispatch it
                    if frame.bytesleft <= 0 and (flags & cont_flag) == 0:
                        message: bytes = (
                            chunks[0] if len(chunks) == 1 else b"".join(chunks)
                        )
                        chunks.clear()
                        current_msg_size = 0

                        try:
                            queue_put_nowait((message, flags))
                        except asyncio.QueueFull:
                            await queue_put((message, flags))

                    msg_counter += 1
                    if (msg_counter & yield_mask) == 0:
                        await asyncio.sleep(0)
                        msg_counter = 0

                    continue

                # Control Frames handled below (Close / Ping)
                # PONG handled: https://everything.curl.dev/helpers/ws/concept.html

                # If a CLOSE frame is received, the reader is done.
                if flags & close_flag:
                    chunks.clear()
                    try:
                        queue_put_nowait((chunk, flags))
                    except asyncio.QueueFull:
                        await queue_put((chunk, flags))
                    await self._handle_close_frame(chunk)
                    return

                # Only applies if CURLWS_RAW_MODE is enabled by the user.
                if flags & ping_flag:
                    try:
                        queue_put_nowait((chunk, flags))
                    except asyncio.QueueFull:
                        await queue_put((chunk, flags))

        except asyncio.CancelledError:
            pass

        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            self._finalize_connection(e)

    async def _write_loop(self) -> None:
        """
        The high-level send manager. It efficiently gathers pending messages
        from the send queue and orchestrates their transmission.

        This method runs a continuous loop that consumes messages from the
        ``_send_queue``. To improve performance and reduce system call overhead,
        it implements an adaptive batching strategy. It greedily gathers
        multiple pending messages from the queue and optionally coalesces the
        payloads of messages that share the same flags (e.g., all text frames)
        into a single, larger payload, ONLY if ``coalesce_frames=True`` and the
        frame is not a CONTROL frame, as the spec requires them to be whole.

        It will batch as many as possible, then iterate over the batch and send
        the frames, one at a time. This batching and coalescing significantly
        improves throughput for high volumes of small messages where the message
        boundaries do not matter. The final, consolidated payloads are then passed
        to the ``_send_payload`` method for transmission.
        """
        control_frame_flags: int = CurlWsFlag.CLOSE | CurlWsFlag.PING
        send_payload: Callable[..., Awaitable[bool]] = self._send_payload
        queue_get: Callable[[], Awaitable[SEND_QUEUE_ITEM]] = self._send_queue.get
        queue_get_nowait: Callable[[], SEND_QUEUE_ITEM] = self._send_queue.get_nowait
        yield_mask: int = self._send_yield_mask
        ops_count = 0

        try:
            while True:
                payload, flags = await queue_get()

                # Build the rest of the batch without waiting.
                batch: list[tuple[bytes, CurlWsFlag]] = [(payload, flags)]
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
                        data_to_coalesce: dict[CurlWsFlag, list[bytes]] = {}
                        for payload, frame in batch:
                            if frame & control_frame_flags:
                                # Flush any pending data before the control frame.
                                for frame_group, payloads in data_to_coalesce.items():
                                    if not await send_payload(
                                        b"".join(payloads), frame_group
                                    ):
                                        return

                                    # Prevent large batches from starving loop
                                    ops_count += 1
                                    if (ops_count & yield_mask) == 0:
                                        await asyncio.sleep(0)
                                        ops_count = 0

                                data_to_coalesce.clear()

                                if not await send_payload(payload, frame):
                                    return

                                # Yield check on coalesced frames
                                ops_count += 1
                                if (ops_count & yield_mask) == 0:
                                    await asyncio.sleep(0)
                                    ops_count = 0

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

                            # Yield check when payload is less than max frame size.
                            ops_count += 1
                            if (ops_count & yield_mask) == 0:
                                await asyncio.sleep(0)
                                ops_count = 0

                finally:
                    # Mark all processed items as done.
                    for _ in range(len(batch)):
                        self._send_queue.task_done()

                # Exit cleanly after sending a CLOSE frame.
                if batch[-1][1] & CurlWsFlag.CLOSE:
                    break

        except asyncio.CancelledError:
            pass

        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            self._finalize_connection(e)

        finally:
            # If the loop exits unexpectedly, ensure we terminate the connection.
            if not self.closed:
                self.terminate()

    async def _send_payload(self, payload: bytes, flags: CurlWsFlag | int) -> bool:
        """
        Optimized low-level sender with fragmentation logic.
        """
        # Cache locals to reduce lookup cost
        curl_ws_send: Callable[[bytes, CurlWsFlag | int], int] = self.curl.ws_send
        loop: asyncio.AbstractEventLoop = self.loop
        sock_fd: int = self._sock_fd
        yield_mask: int = self._send_yield_mask
        max_frame_size: int = self._MAX_CURL_FRAME_SIZE
        e_again: CurlECode = CurlECode.AGAIN
        max_zero_writes: int = 3

        # Message specific values
        view: memoryview = memoryview(payload)
        total_bytes: int = view.nbytes
        base_flags: int = flags & ~CurlWsFlag.CONT
        offset: int = 0
        write_ops: int = 0
        zero_write_retries: int = 0

        # Loop until the entire view is sent
        while offset < total_bytes or (offset == 0 and total_bytes == 0):
            # Calculate the size of the current fragment
            chunk: memoryview = view[
                offset: offset + min(total_bytes - offset, max_frame_size)
            ]
            chunk_len: int = len(chunk)

            # Handle frame fragmentation and prevent CONT leakage.
            current_flags: CurlWsFlag | int = base_flags
            if (offset + chunk_len) < total_bytes:
                current_flags |= CurlWsFlag.CONT

            try:
                # libcurl returns the number of bytes actually sent
                n_sent: int = curl_ws_send(chunk.tobytes(), current_flags)

                if n_sent == 0:
                    # Handle 0-byte payload (Valid Empty Frame)
                    if chunk_len == 0:
                        return True

                    # Raise AGAIN to jump to the existing wait logic below
                    if chunk_len > 0:
                        zero_write_retries += 1
                        if zero_write_retries >= max_zero_writes:
                            self._finalize_connection(
                                WebSocketError(
                                    (
                                        "Writer stalled "
                                        f"({zero_write_retries} attempts)."
                                    ),
                                    CurlECode.WRITE_ERROR,
                                )
                            )
                            return False

                        raise CurlError("0 bytes sent", e_again)

                if zero_write_retries > 0:
                    zero_write_retries = 0

                offset += n_sent

                # Cooperative yield checks
                write_ops += 1
                if (write_ops & yield_mask) == 0:
                    await asyncio.sleep(0)

            except CurlError as e:
                if e.code == e_again:
                    # Wait for socket to be writable
                    write_future: asyncio.Future[None] = loop.create_future()
                    try:
                        loop.add_writer(sock_fd, write_future.set_result, None)
                        await write_future

                    # pylint: disable-next=broad-exception-caught
                    except Exception as exc:
                        self._finalize_connection(
                            WebSocketError(
                                f"Socket closed unexpectedly during write: {exc}",
                                CurlECode.NO_CONNECTION_AVAILABLE,
                            )
                        )
                        return False

                    finally:
                        if sock_fd != -1:
                            with suppress(Exception):
                                _ = loop.remove_writer(sock_fd)

                    # Retry the exact same chunk
                    continue

                # Fatal Error
                self._finalize_connection(e)
                return False

        return True

    async def flush(self, timeout: float | None = None) -> None:
        """Waits until all items in the send queue have been processed.

        This ensures that all messages passed to `send()` have been handed off to the
        underlying socket for transmission. It does not guarantee that the data has
        been received by the remote peer.

        Args:
            timeout (float | None, optional): The maximum number of seconds to wait
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
        tasks_to_cancel: set[asyncio.Task[None]] = {
            t
            for t in (self._read_task, self._write_task)
            if t is not None and not t.done()
        }
        max_timeout: int = 2

        try:
            # Cancel all the I/O tasks
            for io_task in tasks_to_cancel:
                _ = io_task.cancel()

            # Wait for cancellation but don't get stuck
            if tasks_to_cancel:
                _, pending = await asyncio.wait(
                    tasks_to_cancel,
                    timeout=max_timeout,
                    return_when=asyncio.ALL_COMPLETED,
                )
                # Force cancel tasks that didn't complete within timeout.
                for p in pending:
                    _ = p.cancel()

            # Drain the send_queue
            while not self._send_queue.empty():
                try:
                    _ = self._send_queue.get_nowait()
                    self._send_queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    break

            # Remove the reader/writer if still registered
            if self._sock_fd != -1:
                with suppress(Exception):
                    _ = self.loop.remove_reader(self._sock_fd)
                with suppress(Exception):
                    _ = self.loop.remove_writer(self._sock_fd)

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
