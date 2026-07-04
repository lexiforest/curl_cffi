"""
The Curl CFFI WebSocket client implementation.
"""

from __future__ import annotations

from asyncio import (
    ALL_COMPLETED,
    FIRST_COMPLETED,
    AbstractEventLoop,
    CancelledError,
    Event,
    Future,
    InvalidStateError,
    Lock,
    Queue,
    QueueEmpty,
    QueueFull,
    Task,
)
from asyncio import TimeoutError as AsyncTimeout
from asyncio import (
    create_task,
    get_running_loop,
    run_coroutine_threadsafe,
    sleep,
    wait,
    wait_for,
)
from collections.abc import Awaitable, Callable, Generator
from contextlib import suppress
from dataclasses import dataclass, field
from enum import IntEnum
from json import dumps as json_dumps
from json import loads as json_loads
from random import uniform
from selectors import EVENT_READ, EVENT_WRITE, BaseSelector, DefaultSelector
from struct import Struct
from threading import Lock as ThreadLock
from time import monotonic as time_monotonic
from time import sleep as sync_sleep
from typing import TYPE_CHECKING, Final, Literal, TypeVar, final
from warnings import warn as user_warning

from ..aio import CURL_SOCKET_BAD, get_selector
from ..const import CurlECode, CurlFollow, CurlInfo, CurlOpt, CurlWsFlag
from ..curl import Curl, CurlError
from ..utils import CurlCffiWarning
from .exceptions import SessionClosed, Timeout
from .models import Response
from .utils import NOT_SET, NotSetType, set_curl_options

if TYPE_CHECKING:
    from typing_extensions import Self

    from ..const import CurlHttpVersion
    from ..curl import CurlWsFrame
    from ..fingerprints import Fingerprint
    from .cookies import CookieTypes
    from .headers import HeaderTypes
    from .impersonate import BrowserTypeLiteral, ExtraFingerprints, ExtraFpDict
    from .session import AsyncSession, ProxySpec

    T = TypeVar("T")

    OnDataType = Callable[["WebSocket", bytes, CurlWsFrame], None]
    OnMessageType = Callable[["WebSocket", bytes | str], None]
    OnErrorType = Callable[["WebSocket", CurlError], None]
    OnOpenType = Callable[["WebSocket"], None]
    OnCloseType = Callable[["WebSocket", int, str], None]
    RecvQueueItem = tuple[bytes, int]
    SendQueueItem = tuple[bytes | bytearray | memoryview, CurlWsFlag | int]

EventTypeLiteral = Literal["open", "close", "data", "message", "error"]

# Bound struct methods
_STRUCT_PACK_CLOSE: Final[Callable[..., bytes]] = Struct("!H").pack
_STRUCT_UNPACK_CLOSE: Final[Callable[..., tuple[int, ...]]] = Struct("!H").unpack_from


@dataclass
class WebSocketRetryStrategy:
    """Configurable WebSocket policy for retrying failed message receives.

    When enabled, each failed receive attempt will use exponential backoff with
    jitter.

    Calculation: ``delay * 2^(count - 1) ± 10%``

    Args:
        retry: Enable or disable WebSocket message receive retry policy.
        delay: The base value (seconds) to compute the retry delay from.
        count: How many times to retry a receive operation before giving up.
        codes: Set of ``CurlECode`` values for which the receive operation
            should be retried. Default is ``CurlECode.RECV_ERROR``.
    """

    retry: bool = False
    delay: float = 0.3
    count: int = 3
    codes: set[CurlECode] = field(default_factory=lambda: {CurlECode.RECV_ERROR})


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

    def __init__(self, message: str, code: WsCloseCode | CurlECode | int = 0) -> None:
        super().__init__(message, code)  # pyright: ignore[reportUnknownMemberType]


class WebSocketClosed(  # pyright: ignore[reportUnsafeMultipleInheritance]
    WebSocketError, SessionClosed
):
    """WebSocket is already closed."""


class WebSocketTimeout(  # pyright: ignore[reportUnsafeMultipleInheritance]
    WebSocketError, Timeout
):
    """WebSocket operation timed out."""


def _safe_set_result(fut: Future[None]) -> None:
    """
    Called by the event loop when fd becomes readable/writable.

    We try to set_result() and silently ignore InvalidStateError which is
    raised if the future was already finished/cancelled concurrently.
    This avoids spurious 'Exception in callback' traces in uvloop/asyncio.

    Intentionally using try/except, cheaper than checking if the future is done.
    """
    try:  # noqa: SIM105
        fut.set_result(None)
    except InvalidStateError:
        pass


class BaseWebSocket:
    """Shared methods and static constants."""

    __slots__: tuple[str, ...] = (
        "_curl",
        "autoclose",
        "_close_code",
        "_close_reason",
        "debug",
        "closed",
        "_max_message_size",
        "ws_retry",
        "_sock_fd",
    )

    _MAX_CURL_FRAME_SIZE: Final[int] = 65536
    _MAX_CONTROL_FRAME_SIZE: Final[int] = 125

    def __init__(
        self,
        curl: Curl | NotSetType = NOT_SET,
        *,
        autoclose: bool = True,
        debug: bool = False,
        ws_retry: WebSocketRetryStrategy | None = None,
        max_message_size: int = 4 * 1024 * 1024,
    ) -> None:
        self._curl: Curl | NotSetType = curl
        self.autoclose: bool = autoclose
        self._close_code: int | None = None
        self._close_reason: str | None = None
        self.debug: bool = debug
        self.closed: bool = False
        self.ws_retry: WebSocketRetryStrategy = ws_retry or WebSocketRetryStrategy()
        self._max_message_size: int = max_message_size
        self._sock_fd: int = -1

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

    def _get_sock_fd(self) -> int:
        """Fetch and cache the active socket file descriptor."""
        sock_fd: int = self._sock_fd
        if sock_fd != -1:
            return sock_fd

        sock_info: bytes | int | float | list[str | int] = self.curl.getinfo(
            CurlInfo.ACTIVESOCKET
        )
        if not isinstance(sock_info, int) or sock_info == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE
            )

        self._sock_fd = sock_info
        return sock_info

    def _prepare_ping_payload(self, payload: str | bytes) -> bytes:
        """Validate and encode ping payloads with robust isinstance checks."""
        payload_bytes: bytes = (
            payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        )
        if len(payload_bytes) > self._MAX_CONTROL_FRAME_SIZE:
            raise WebSocketError(
                f"Ping frame has invalid length: {len(payload_bytes)}",
                CurlECode.TOO_LARGE,
            )
        return payload_bytes

    def _pack_close_frame(self, code: int, reason: bytes) -> bytes:
        """Pack close code and reason using cached Struct.pack method."""
        return _STRUCT_PACK_CLOSE(code) + reason

    def _unpack_close_frame(self, frame: bytes) -> tuple[int, str]:
        """Unpack close frame using cached Struct.unpack method."""
        if len(frame) < 2:
            return WsCloseCode.UNKNOWN, ""

        try:
            return _STRUCT_UNPACK_CLOSE(frame)[0], frame[2:].decode("utf-8")
        except UnicodeDecodeError as e:
            raise WebSocketError(
                "Invalid close message", WsCloseCode.INVALID_DATA
            ) from e
        except Exception as e:
            raise WebSocketError(
                "Invalid close frame", WsCloseCode.PROTOCOL_ERROR
            ) from e

    def _set_close_state(self, frame: bytes) -> int:
        """Unpacks the close frame, sets internal state, and returns fallback code."""
        try:
            self._close_code, self._close_reason = self._unpack_close_frame(frame)
        except WebSocketError as e:
            self._close_code = e.code

        code: int | CurlECode = self._close_code
        if code == WsCloseCode.UNKNOWN:
            return WsCloseCode.OK

        return code

    def terminate(self) -> None:
        """Terminate the underlying connection."""
        self.closed = True
        self.curl.close()


@final
class WebSocket(BaseWebSocket):
    """A high-performance synchronous WebSocket implementation using libcurl."""

    __slots__ = (
        "skip_utf8_validation",
        "_emitters",
        "keep_running",
        "_read_selector",
        "_write_selector",
    )

    def __init__(
        self,
        curl: Curl | NotSetType = NOT_SET,
        *,
        autoclose: bool = True,
        skip_utf8_validation: bool = False,
        debug: bool = False,
        on_open: OnOpenType | None = None,
        on_close: OnCloseType | None = None,
        on_data: OnDataType | None = None,
        on_message: OnMessageType | None = None,
        on_error: OnErrorType | None = None,
        ws_retry: WebSocketRetryStrategy | None = None,
        max_message_size: int = 4 * 1024 * 1024,
    ) -> None:
        """
        Args:
            curl (Curl | NotSetType, optional): Curl handle.
            autoclose (bool, optional): Whether to close the WebSocket
                after receiving a close frame.
            skip_utf8_validation (bool, optional): Whether to skip UTF-8
                validation for text frames in run_forever().
            debug (bool, optional): Print extra curl debug info.
            on_open (OnOpenType | None, optional): Open callback.
            on_close (OnCloseType | None, optional): Close callback.
            on_data (OnDataType | None, optional): Data received callback.
            on_message (OnMessageType | None, optional): Message received callback.
            on_error (OnErrorType | None, optional): Error callback.
            ws_retry (WebSocketRetryStrategy | None, optional): Retry policy.
            max_message_size (int, optional): Message size limit.
        """
        super().__init__(
            curl=curl,
            autoclose=autoclose,
            debug=debug,
            ws_retry=ws_retry,
            max_message_size=max_message_size,
        )
        self.skip_utf8_validation: bool = skip_utf8_validation
        self.keep_running: bool = False
        self._read_selector: BaseSelector | None = None
        self._write_selector: BaseSelector | None = None

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

    def _get_sock_fd(self) -> int:  # pyright: ignore[reportImplicitOverride]
        """Fetch socket and lazily-initialize native selectors for polling."""
        sock_fd: int = super()._get_sock_fd()

        if self._read_selector is None:
            r_sel: DefaultSelector = DefaultSelector()
            _ = r_sel.register(sock_fd, EVENT_READ)
            self._read_selector = r_sel

            w_sel: DefaultSelector = DefaultSelector()
            _ = w_sel.register(sock_fd, EVENT_WRITE)
            self._write_selector = w_sel

        return sock_fd

    def __iter__(self) -> WebSocket:
        if self.closed:
            raise WebSocketClosed("WebSocket is closed")
        return self

    def __next__(self) -> bytes:
        try:
            msg, flags = self.recv()
        except WebSocketClosed:
            raise StopIteration from None

        if flags & CurlWsFlag.CLOSE:
            raise StopIteration
        return msg

    def __enter__(self) -> Self:
        """Enable context manager usage for automatic session management."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object | None,
    ) -> None:
        """Close the WebSocket connection on exiting the context manager."""
        if exc_type is None:
            self.close()
        else:
            # Don't mask existing exception during teardown
            with suppress(CurlError, WebSocketTimeout):
                self.close()

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
                    user_warning(
                        f"WebSocket callback '{event_type}' failed",
                        CurlCffiWarning,
                        stacklevel=2,
                    )

    def _handle_close_frame(self, message: bytes) -> None:
        """Robustly process a CLOSE frame without loop overhead."""
        close_code: int = self._set_close_state(message)
        if self.autoclose and not self.closed:
            self.close(close_code)
        else:
            self.terminate()

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
        allow_redirects: bool | CurlFollow | str = True,
        max_redirects: int = 30,
        proxies: ProxySpec | None = None,
        proxy: str | None = None,
        proxy_auth: tuple[str, str] | None = None,
        verify: bool | None = None,
        referer: str | None = None,
        accept_encoding: str | None = "gzip, deflate, br",
        impersonate: BrowserTypeLiteral | str | Fingerprint | None = None,
        ja3: str | None = None,
        akamai: str | None = None,
        perk: str | None = None,
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
            allow_redirects: whether to allow redirection. Can be a bool, a
                ``CurlFollow`` value, or the string ``"safe"``.
            max_redirects: max redirect counts, default 30, use -1 for unlimited.
            proxies: dict of proxies to use, prefer to use ``proxy`` if they are the
                same. format: ``{"http": proxy_url, "https": proxy_url}``.
            proxy: proxy to use, format: "http://user@pass:proxy_url".
                Can't be used with `proxies` parameter.
            proxy_auth: HTTP basic auth for proxy, a tuple of (username, password).
            verify: whether to verify https certs.
            referer: shortcut for setting referer header.
            accept_encoding: shortcut for setting accept-encoding header.
            impersonate: which browser version or fingerprint to impersonate.
            ja3: ja3 string to impersonate.
            akamai: akamai string to impersonate.
            perk: perk string to impersonate.
            extra_fp: extra fingerprints options, in complement to ja3 and akamai str.
            default_headers: whether to set default browser headers.
            default_encoding: Encoding for decoding content if charset is not found.
                Defaults to "utf-8".
            quote: Set characters to be quoted (percent-encoded). Default safe
                string is ``!#$%&'()*+,/:;=?@[]~``. If set to a string, the characters
                will be removed from the safe string. If set to ``False``, the URL
                is used as-is (you must encode it yourself).
            http_version: Limiting http version, defaults to http2.
            interface: interface name or local IP to bind to (bare IP = source address).
            cert: a tuple of (cert, key) filenames for client cert.
            max_recv_speed: maximum receive speed, bytes per second.
            curl_options: extra curl options to use.

        Note:
            The ``WebSocket`` is NOT thread-safe, add your own locking
            or use ``AsyncWebSocket`` for concurrent sending and receiving.
        """

        # Reset socket and selector cache
        self._sock_fd = -1
        if self._read_selector is not None:
            self._read_selector.close()
            self._read_selector = None
        if self._write_selector is not None:
            self._write_selector.close()
            self._write_selector = None

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
            perk=perk,
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
        _ = curl.setopt(CurlOpt.TCP_NODELAY, 1)
        _ = curl.setopt(CurlOpt.CONNECT_ONLY, 2)
        curl.perform()
        return self

    def recv(self, *, timeout: float | None = None) -> tuple[bytes, int]:
        """Receive a WebSocket message.

        This method waits for and returns the next complete WebSocket message.
        Attempts to read immediately and only polls the socket if it returns EAGAIN.

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
            This method is NOT thread-safe.

            Message fragmentation and reassembly are handled automatically by the
            implementation, so callers will always receive complete messages.
        """
        if self.closed:
            raise WebSocketClosed("WebSocket is closed")

        _ = self._get_sock_fd()
        read_selector: BaseSelector | None = self._read_selector
        if read_selector is None:
            raise WebSocketError("Selectors uninitialized", CurlECode.FAILED_INIT)

        # Cache local variables
        retry_on_error: bool = self.ws_retry.retry
        retry_codes: set[CurlECode] = self.ws_retry.codes
        max_retries: int = self.ws_retry.count
        retry_base: float = float(self.ws_retry.delay)
        recv_error_retries: int = 0
        max_message_size: int = self._max_message_size
        curl_ws_recv: Callable[[], tuple[bytes, CurlWsFrame]] = self.curl.ws_recv
        chunks: list[bytes] = []
        chunks_append: Callable[[bytes], None] = chunks.append
        msg_size: int = 0
        flags: int = 0
        deadline: float = 0.0
        if timeout is not None:
            deadline = time_monotonic() + timeout

        # Merged bitmasks to minimize hot-loop branching
        close_flag: int = int(CurlWsFlag.CLOSE)
        cont_flag: int = int(CurlWsFlag.CONT)
        data_mask: int = CurlWsFlag.BINARY | CurlWsFlag.TEXT | cont_flag

        while True:
            try:
                # Read WebSocket frame from libcurl
                chunk, frame = curl_ws_recv()
                if recv_error_retries > 0:
                    recv_error_retries = 0

                flags = frame.flags

                # Data Frames (Text / Binary / Cont)
                if flags & data_mask:

                    # Perform message size checks
                    msg_size += len(chunk)
                    if msg_size > max_message_size:
                        chunks.clear()
                        self.close(WsCloseCode.MESSAGE_TOO_BIG, b"Message too large")
                        raise WebSocketError(
                            f"Message too large: {msg_size} bytes.", CurlECode.TOO_LARGE
                        )
                    chunks_append(chunk)

                    # If the message is complete, process and dispatch it
                    if frame.bytesleft == 0 and not (flags & cont_flag):
                        break

                    continue

                # If a CLOSE frame is received, the reader is done.
                if flags & close_flag:
                    self._handle_close_frame(chunk)
                    return chunk, flags

                # Silently consume PING/PONG and loop again
                continue

            except CurlError as e:
                code: int = e.code
                should_retry: bool = False

                # Handle normal cURL EAGAINs
                if code == CurlECode.AGAIN:
                    should_retry = True

                # EAGAIN ("errno 11") bubbling up as RECV_ERROR from BoringSSL
                elif code == CurlECode.RECV_ERROR:
                    err_msg: str = str(e).lower()
                    if (
                        "errno 11" in err_msg
                        or "resource temporarily unavailable" in err_msg
                    ):
                        should_retry = True

                # Handle Server Disconnect (Empty Reply)
                elif code == CurlECode.GOT_NOTHING:
                    raise WebSocketClosed(
                        "Server EOF", WsCloseCode.ABNORMAL_CLOSURE
                    ) from e

                if should_retry:
                    if timeout is not None:
                        if not read_selector.select(deadline - time_monotonic()):
                            raise WebSocketTimeout(
                                "WebSocket recv() timed out",
                                CurlECode.OPERATION_TIMEDOUT,
                            ) from None
                    else:
                        _ = read_selector.select(None)
                    continue

                # Apply the user-configured retry logic
                if (
                    retry_on_error
                    and code in retry_codes
                    and recv_error_retries < max_retries
                ):
                    recv_error_retries += 1
                    # Formula: base * (2 ^ (attempt - 1)) + jitter (+/- 10%)
                    retry_delay: float = retry_base * (  # pyright: ignore[reportAny]
                        2 ** (recv_error_retries - 1)
                    )
                    sleep_time: float = max(
                        0.0,
                        retry_delay + uniform(-retry_delay * 0.1, retry_delay * 0.1),
                    )

                    # Check if user timeout is configured
                    if timeout is not None:
                        remain = deadline - time_monotonic()
                        if sleep_time > remain:
                            # Sleep exactly until the deadline.
                            sync_sleep(max(0.0, remain))
                            continue

                    sync_sleep(sleep_time)
                    continue

                # Fatal error - can't retry
                raise

        return chunks[0] if len(chunks) == 1 else b"".join(chunks), flags

    def recv_str(self, *, timeout: float | None = None) -> str:
        """Receive a text frame."""
        data, flags = self.recv(timeout=timeout)
        if flags & CurlWsFlag.CLOSE:
            raise WebSocketClosed(
                f"Received close frame: {self.close_code} {self.close_reason}",
                self.close_code or WsCloseCode.OK,
            )

        if not (flags & CurlWsFlag.TEXT):
            raise WebSocketError("Not a valid text frame", WsCloseCode.INVALID_DATA)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise WebSocketError(
                "Invalid UTF-8 in text frame", WsCloseCode.INVALID_DATA
            ) from e

    def recv_json(
        self, *, loads: Callable[[str], T] = json_loads, timeout: float | None = None
    ) -> T:
        """Receive a JSON frame."""
        data: str = self.recv_str(timeout=timeout)
        if not data:
            raise WebSocketError("Empty frame", WsCloseCode.INVALID_DATA)
        try:
            return loads(data)
        except Exception as e:
            raise WebSocketError(f"Invalid JSON: {e}", WsCloseCode.INVALID_DATA) from e

    def recv_fragment(self) -> tuple[bytes, CurlWsFrame]:
        """This function is deprecated and removed.
        The new architecture automatically handles frame reassembly.
        Call :meth:`recv()` instead to get complete, fully assembled frames.
        """
        raise NotImplementedError(
            "recv_fragment() is no longer supported. "
            + "Call recv() instead to get complete messages. "
            + "See docs: https://curl-cffi.readthedocs.io/en/latest/websockets.html"
        )

    def send(
        self,
        payload: str | bytes | bytearray | memoryview,
        flags: CurlWsFlag | int = CurlWsFlag.BINARY,
        timeout: float | None = None,
    ) -> int:
        """
        Send a WebSocket message.

        Args:
            payload: Data to send (``str``/``bytes``/``bytearray``/``memoryview``).
            flags: Frame type flags (e.g., ``CurlWsFlag.TEXT`` / ``CurlWsFlag.BINARY``).
            timeout: Max seconds to wait if the socket is blocked.

        Returns:
            ``int``: The number of bytes successfully written to the socket.

        Raises:
            CurlError: Network related exception occured.
            WebSocketClosed: The WebSocket has been closed.
            WebSocketTimeout: The send operation timed out.

        Note:
            This method is NOT thread-safe.

            There are no limits on the size of the message that can be sent.
            Large outbound messages are seamlessly broken down into optimal
            fragments using the ``CURLWS_CONT`` flag, arriving as a single
            logical message to the server.
        """
        if flags & CurlWsFlag.CLOSE:
            self.keep_running = False

        if self.closed:
            raise WebSocketClosed("WebSocket is already closed")

        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        _ = self._get_sock_fd()
        write_selector: BaseSelector | None = self._write_selector
        if write_selector is None:
            raise WebSocketError("Selectors uninitialized", CurlECode.FAILED_INIT)

        view: memoryview = memoryview(payload)
        total_bytes: int = view.nbytes
        offset: int = 0
        frame_end: int = 0
        write_retries: int = 0
        max_zero_writes: int = 3

        # Hoist locals
        base_flags: int = flags & ~CurlWsFlag.CONT
        current_flags: int = flags
        max_frame_size: int = self._MAX_CURL_FRAME_SIZE
        curl_ws_send: Callable[..., int] = self.curl.ws_send

        deadline: float = 0.0
        if timeout is not None:
            deadline = time_monotonic() + timeout

        # Loop until the entire view is sent
        while offset < total_bytes or (offset == 0 and total_bytes == 0):
            # Boundary check: Calculate next fragment ONLY when needed
            if offset == frame_end:
                if total_bytes - offset > max_frame_size:
                    frame_end = offset + max_frame_size
                    current_flags = base_flags | CurlWsFlag.CONT
                else:
                    frame_end = total_bytes
                    current_flags = flags

            try:
                # libcurl returns the number of bytes actually sent
                n_sent: int = curl_ws_send(view[offset:frame_end], current_flags)

                if n_sent == 0:
                    # Handle 0-byte payload (Valid Empty Frame)
                    if frame_end - offset == 0:
                        return offset

                    # Raise AGAIN to jump to the existing wait logic below
                    write_retries += 1
                    if write_retries >= max_zero_writes:
                        raise WebSocketError(
                            f"Writer stalled ({write_retries} attempts).",
                            CurlECode.WRITE_ERROR,
                        )
                    raise CurlError("0 bytes sent", CurlECode.AGAIN)

                if write_retries:
                    write_retries = 0

                offset += n_sent

            except CurlError as e:
                code: int = e.code
                retry_eagain: bool = False

                # Handle normal cURL EAGAINs
                if code == CurlECode.AGAIN:
                    retry_eagain = True

                # EAGAIN ("errno 11") bubbling up as SEND_ERROR from BoringSSL
                elif code == CurlECode.SEND_ERROR:
                    err_msg: str = str(e).lower()
                    if (
                        "errno 11" in err_msg
                        or "resource temporarily unavailable" in err_msg
                    ):
                        retry_eagain = True

                if retry_eagain:
                    # Check the clock when the socket is blocked
                    try:
                        if timeout is not None:
                            if not write_selector.select(deadline - time_monotonic()):
                                raise WebSocketTimeout(
                                    "Socket write timeout", CurlECode.OPERATION_TIMEDOUT
                                ) from None
                        else:
                            _ = write_selector.select(None)
                    except (ValueError, OSError) as exc:
                        if self.closed:
                            raise WebSocketClosed("WebSocket is closed") from exc
                        raise

                    continue
                raise

        return offset

    def send_binary(self, payload: bytes, *, timeout: float | None = None) -> int:
        """Send a binary frame."""
        return self.send(payload, CurlWsFlag.BINARY, timeout=timeout)

    def send_bytes(self, payload: bytes, *, timeout: float | None = None) -> int:
        """Send a binary frame, alias of :meth:`send_binary`."""
        return self.send(payload, CurlWsFlag.BINARY, timeout=timeout)

    def send_str(self, payload: str, *, timeout: float | None = None) -> int:
        """Send a text frame."""
        return self.send(payload, CurlWsFlag.TEXT, timeout=timeout)

    def send_json(
        self,
        payload: object,
        *,
        dumps: Callable[..., str] = json_dumps,
        timeout: float | None = None,
    ) -> int:
        """Send a JSON frame.

        Args:
            payload: data to send.
            dumps: JSON encoder, default is json.dumps.
        """
        if dumps is json_dumps:
            return self.send_str(
                json_dumps(payload, separators=(",", ":")), timeout=timeout
            )
        return self.send_str(dumps(payload), timeout=timeout)

    def ping(self, payload: str | bytes, *, timeout: float | None = None) -> int:
        """Send a ping frame."""
        return self.send(
            self._prepare_ping_payload(payload), CurlWsFlag.PING, timeout=timeout
        )

    def run_forever(
        self,
        url: str = "",
        **kwargs,  # pyright: ignore[reportUnknownParameterType, reportMissingParameterType]
    ) -> None:
        """Run the WebSocket forever. See :meth:`connect` for details on parameters.

        libcurl automatically handles pings and pongs.
        ref: https://curl.se/libcurl/c/libcurl-ws.html
        """
        if url:
            _ = self.connect(
                url, **kwargs  # pyright: ignore[reportUnknownArgumentType]
            )

        _ = self._get_sock_fd()
        read_selector: BaseSelector | None = self._read_selector
        if read_selector is None:
            raise WebSocketError("Selectors uninitialized", CurlECode.FAILED_INIT)

        self._emit("open")

        # Hoist locals
        chunks: list[bytes] = []
        chunks_append: Callable[[bytes], None] = chunks.append
        chunks_clear: Callable[[], None] = chunks.clear
        msg_size: int = 0
        self.keep_running = True

        retry_on_error: bool = self.ws_retry.retry
        retry_codes: set[CurlECode] = self.ws_retry.codes
        max_retries: int = self.ws_retry.count
        retry_base: float = float(self.ws_retry.delay)
        recv_error_retries: int = 0

        max_message_size: int = self._max_message_size
        curl_ws_recv: Callable[[], tuple[bytes, CurlWsFrame]] = self.curl.ws_recv
        emit: Callable[..., None] = self._emit
        has_message_emitter: bool = "message" in self._emitters

        close_flag: int = int(CurlWsFlag.CLOSE)
        cont_flag: int = int(CurlWsFlag.CONT)
        data_mask: int = CurlWsFlag.BINARY | CurlWsFlag.TEXT | cont_flag

        while self.keep_running:
            try:
                # Read WebSocket frame
                chunk, frame = curl_ws_recv()
                if recv_error_retries > 0:
                    recv_error_retries = 0

                flags: int = frame.flags
                emit("data", chunk, frame)

                # Data Frames (Text / Binary / Cont)
                if flags & data_mask:
                    # Perform message size checks
                    msg_size += len(chunk)
                    if msg_size > max_message_size:
                        chunks_clear()
                        self.close(WsCloseCode.MESSAGE_TOO_BIG)

                        # Emit the close event before raising
                        emit(
                            "close",
                            self._close_code or WsCloseCode.MESSAGE_TOO_BIG,
                            self._close_reason or "",
                        )

                        raise WebSocketError(
                            (
                                f"Message too large: {msg_size} bytes "
                                f"(limit {max_message_size} bytes)."
                            ),
                            CurlECode.TOO_LARGE,
                        )

                    # Collect the chunk
                    chunks_append(chunk)

                    # If the message is complete, process and dispatch it
                    if not (frame.bytesleft == 0 and not (flags & cont_flag)):
                        continue

                    if has_message_emitter:
                        msg: bytes = chunks[0] if len(chunks) == 1 else b"".join(chunks)

                        if (flags & CurlWsFlag.TEXT) and not self.skip_utf8_validation:
                            try:
                                emit_msg: str | bytes = msg.decode("utf-8")
                            except UnicodeDecodeError as e:
                                self._close_code = WsCloseCode.INVALID_DATA
                                self.close(WsCloseCode.INVALID_DATA)
                                emit(
                                    "close", self._close_code, self._close_reason or ""
                                )
                                raise WebSocketError(
                                    "Invalid UTF-8", WsCloseCode.INVALID_DATA
                                ) from e
                        else:
                            emit_msg = msg

                        if (flags & CurlWsFlag.BINARY) or (flags & CurlWsFlag.TEXT):
                            emit("message", emit_msg)

                    chunks_clear()
                    msg_size = 0
                    continue

                # If a CLOSE frame is received, the reader is done.
                if flags & close_flag:
                    self._handle_close_frame(chunk)
                    self.keep_running = False
                    emit("close", self._close_code or 0, self._close_reason or "")
                    break

                # Silently consume PING/PONG and loop again
                if flags & (CurlWsFlag.PING | CurlWsFlag.PONG):
                    continue

            except CurlError as e:
                should_retry: bool = False
                code: int = e.code

                # Handle normal cURL EAGAINs
                if code == CurlECode.AGAIN:
                    should_retry = True

                # EAGAIN ("errno 11") bubbling up as RECV_ERROR from BoringSSL
                elif code == CurlECode.RECV_ERROR:
                    err_msg: str = str(e).lower()
                    if (
                        "errno 11" in err_msg
                        or "resource temporarily unavailable" in err_msg
                    ):
                        should_retry = True

                # Handle Server Disconnect (Empty Reply)
                elif code == CurlECode.GOT_NOTHING:
                    e_close: WebSocketClosed = WebSocketClosed(
                        "Connection closed unexpectedly by server (EOF)",
                        WsCloseCode.ABNORMAL_CLOSURE,
                    )
                    e_close.__suppress_context__ = True
                    self.keep_running = False
                    emit("error", e_close)
                    self.close(WsCloseCode.ABNORMAL_CLOSURE)
                    emit(
                        "close",
                        self._close_code or WsCloseCode.ABNORMAL_CLOSURE,
                        self._close_reason or "",
                    )
                    raise e_close from e

                if should_retry:
                    _ = read_selector.select(0.5)
                    continue

                # Apply the user-configured retry logic
                if (
                    self.keep_running
                    and retry_on_error
                    and code in retry_codes
                    and recv_error_retries < max_retries
                ):
                    recv_error_retries += 1
                    # Formula: base * (2 ^ (attempt - 1))
                    retry_delay: float = retry_base * (  # pyright: ignore[reportAny]
                        2 ** (recv_error_retries - 1)
                    )
                    # Add Jitter: +/- 10%
                    jitter: float = retry_delay * 0.1
                    sync_sleep(max(0.0, retry_delay + uniform(-jitter, jitter)))
                    continue

                # Fatal error
                emit("error", e)
                if not self.closed:
                    close_code: int = WsCloseCode.UNKNOWN
                    if isinstance(e, WebSocketError):
                        close_code = e.code
                    self.close(close_code)
                    emit(
                        "close",
                        self._close_code or close_code,
                        self._close_reason or "",
                    )
                raise

    def close(
        self,
        code: int = WsCloseCode.OK,
        message: str | bytes = b"",
        timeout: float = 3.0,
    ) -> None:
        """Close the connection.

        Args:
            code: close code.
            message: close reason.
            timeout: Max seconds to wait for the close frame to send.
        """
        if self.closed:
            return

        if isinstance(message, str):
            message = message.encode("utf-8")

        max_msg_size: int = self._MAX_CONTROL_FRAME_SIZE - 2
        if len(message) > max_msg_size:
            message = message[:max_msg_size]

        if self._close_code is None:
            self._close_code = code
            self._close_reason = message.decode("utf-8", errors="replace")

        msg: bytes = self._pack_close_frame(code, message)
        with suppress(CurlError):
            _ = self.send(msg, CurlWsFlag.CLOSE, timeout=timeout)

        self.terminate()

    def terminate(self) -> None:  # pyright: ignore[reportImplicitOverride]
        """Terminate the connection and clean up selectors."""
        if self._read_selector is not None:
            self._read_selector.close()
            self._read_selector = None

        if self._write_selector is not None:
            self._write_selector.close()
            self._write_selector = None

        super().terminate()


@final
class AsyncWebSocket(BaseWebSocket):
    """
    A high-performance asynchronous WebSocket implementation using libcurl.
    """

    __slots__ = (
        "session",
        "_loop",
        "_close_lock",
        "_terminate_lock",
        "_read_task",
        "_write_task",
        "_receive_queue",
        "_send_queue",
        "_max_send_batch_size",
        "_coalesce_frames",
        "_recv_time_slice",
        "_send_time_slice",
        "_terminated",
        "_terminated_event",
        "_transport_exception",
        "drain_on_error",
        "_block_on_recv_queue_full",
    )

    def __init__(
        self,
        session: AsyncSession,
        curl: Curl,
        *,
        autoclose: bool = True,
        debug: bool = False,
        recv_queue_size: int = 64,
        send_queue_size: int = 32,
        max_send_batch_size: int = 64,
        coalesce_frames: bool = False,
        ws_retry: WebSocketRetryStrategy | None = None,
        recv_time_slice: float = 0.01,
        send_time_slice: float = 0.01,
        max_message_size: int = 4 * 1024 * 1024,
        drain_on_error: bool = False,
        block_on_recv_queue_full: bool = True,
    ) -> None:
        """Initializes an Async WebSocket session.

        Do not instantiate this class directly. Use ``AsyncSession.ws_connect``.

        This class implements an async context manager, closing the connection
        automatically on exit:

        ::

            async with AsyncSession() as session:
                async with session.ws_connect("wss://api.example.com") as ws:
                    await ws.send("Hello")
                    msg = await ws.recv()

        Args:
            session (AsyncSession): The parent session object.
            curl (Curl): The underlying Curl handle.
            autoclose (bool): Automatically close on receiving a close frame.
            debug (bool): Enable verbose debug logging.
            recv_queue_size (int): Max number of incoming messages to buffer.
            send_queue_size (int): Max number of outgoing messages to buffer.
            max_send_batch_size (int): Max frames to coalesce per transmission.
            coalesce_frames (bool): Combine small frame payloads to improve throughput.
            ws_retry (WebSocketRetryStrategy): Retry configuration for failed receives.
            recv_time_slice (float): Max seconds to read messages before yielding.
            send_time_slice (float): Max seconds to write messages before yielding.
            max_message_size (int): Max size (bytes) of a single received message.
            drain_on_error (bool): Yield buffered messages before raising errors.
            block_on_recv_queue_full (bool): Behavior when the receive queue is full.
                If True (default), the reader blocks (may cause timeouts).
                If False, the connection fails immediately to prevent data loss.

        Note:
            Architecture: This uses a background I/O model. Network operations run in
            background tasks. Network errors are raised in calls to send() or recv().

            Performance: Time slices default to 10ms. Increase these values to allocate
            more CPU time to I/O operations at the cost of event loop latency.

            Increasing queue sizes reduces backpressure and buffers more messages
            in memory, increasing throughput - but increases latency and bufferbloat.

        See also:
            - https://curl.se/libcurl/c/curl_ws_recv.html
            - https://curl.se/libcurl/c/curl_ws_send.html
        """
        super().__init__(
            curl=curl,
            autoclose=autoclose,
            debug=debug,
            ws_retry=ws_retry,
            max_message_size=max_message_size,
        )
        self.session: AsyncSession[Response] = session
        self._loop: AbstractEventLoop | None = None
        self._terminated: bool = False
        self._close_lock: Lock = Lock()
        self._terminate_lock: ThreadLock = ThreadLock()
        self._terminated_event: Event = Event()
        self._read_task: Task[None] | None = None
        self._write_task: Task[None] | None = None
        self._receive_queue: Queue[RecvQueueItem] = Queue(maxsize=recv_queue_size)
        self._send_queue: Queue[SendQueueItem] = Queue(maxsize=send_queue_size)
        self._max_send_batch_size: int = max_send_batch_size
        self._coalesce_frames: bool = coalesce_frames
        self._recv_time_slice: float = recv_time_slice
        self._send_time_slice: float = send_time_slice
        self._transport_exception: Exception | None = None
        self.drain_on_error: bool = drain_on_error
        self._block_on_recv_queue_full: bool = block_on_recv_queue_full

    @property
    def loop(self) -> AbstractEventLoop:
        """Get a reference to the running event loop"""
        if self._loop is None:
            self._loop = get_selector(get_running_loop())
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
        if exc_type is None:
            await self.close()
        else:
            # Don't mask existing exception.
            with suppress(CurlError):
                await self.close()

    def __aiter__(self) -> Self:
        if self.closed:
            raise WebSocketClosed("WebSocket has been closed")
        return self

    async def __anext__(self) -> bytes:
        try:
            msg, flags = await self.recv()
        except WebSocketClosed:
            raise StopAsyncIteration from None

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

    def _start_io_tasks(self) -> None:  # pyright: ignore[reportUnusedFunction]
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

        # Get the currently active socket FD
        self._sock_fd = self._get_sock_fd()

        # Get an identifier for the websocket from its object id
        ws_id: str = f"WebSocket-{id(self):#x}"

        # Start the I/O loop tasks
        self._read_task = self.loop.create_task(
            self._read_loop(), name=f"{ws_id}-reader"
        )
        self._write_task = self.loop.create_task(
            self._write_loop(), name=f"{ws_id}-writer"
        )

    async def _handle_close_frame(self, message: bytes) -> None:
        """Unpack and handle the closing frame, then initiate shutdown."""
        close_code = self._set_close_state(message)
        if self.autoclose and not self.closed:
            await self.close(close_code)
        else:
            self.terminate()

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
            Message fragmentation and reassembly are handled automatically by the
            implementation, so callers will always receive complete messages.

            ``WebSocketError`` exceptions may have originated from prior
            ``send()`` or ``recv()`` operations, since all operations
            share the same transport state once a failure occurs.

            This method does not wait for additional messages after a transport
            error is detected. If ``drain_on_error=True``, subsequent calls to
            ``recv()`` will return any messages that were buffered in the receive
            queue at the time the reader failed, before the connection error is raised.

            Concurrent calls to ``recv()`` are supported and safe; each caller
            awaits the next available message and will receive distinct messages
            in FIFO order.

            If this coroutine is cancelled while a message is being received,
            that message may be dropped. Cancellation is treated as abandoning
            the receive operation.
        """
        # Fast-fail when transport already errored and we aren't draining.
        if self._transport_exception is not None and not self.drain_on_error:
            raise self._transport_exception

        # Hot path: immediate buffered item (zero allocation).
        try:
            return self._receive_queue.get_nowait()
        except QueueEmpty:
            pass

        # Terminal checks when queue is empty.
        if self._transport_exception is not None:
            raise self._transport_exception

        if self._read_task is None or self._read_task.done():
            raise WebSocketClosed("WebSocket is closed")

        # Cold path: wait for data or for the reader task to finish.
        queue_waiter: Task[RecvQueueItem] = create_task(self._receive_queue.get())

        try:
            # Wait for the first of: queue_waiter or _read_task
            done, _ = await wait(
                (queue_waiter, self._read_task),
                return_when=FIRST_COMPLETED,
                timeout=timeout,
            )

        # Caller cancelled — cancel the waiter and re-raise
        except CancelledError:
            if not queue_waiter.done():
                _ = queue_waiter.cancel()
                with suppress(CancelledError):
                    await queue_waiter
            raise

        # Timeout occurred and no message
        if not done:
            _ = queue_waiter.cancel()
            try:
                return await queue_waiter
            except CancelledError:
                pass

            # Prefer transport error over timeout if both happen
            if self._transport_exception is not None:
                raise self._transport_exception

            raise WebSocketTimeout(
                "WebSocket recv() timed out", CurlECode.OPERATION_TIMEDOUT
            )

        # If queue_waiter completed first, return its result.
        if queue_waiter in done:
            return await queue_waiter

        # Reader task finished first. Cancel the waiter.
        _ = queue_waiter.cancel()
        with suppress(CancelledError):
            await queue_waiter

        # Try to return one buffered item when drain is set
        if self.drain_on_error:
            with suppress(QueueEmpty):
                return self._receive_queue.get_nowait()

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
        if flags & CurlWsFlag.CLOSE:
            raise WebSocketClosed(
                f"Received close frame: {self.close_code} {self.close_reason}",
                self.close_code or WsCloseCode.OK,
            )

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
        loads: Callable[[str], T] = json_loads,
        timeout: float | None = None,
    ) -> T:
        """Receive a JSON frame.

        Args:
            loads: JSON decoder, default is :meth:`json.loads`.
            timeout: how many seconds to wait before giving up.

        Raises:
            WebSocketError: Received frame is invalid or failed to decode JSON.
        """
        data: str = await self.recv_str(timeout=timeout)
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
        flags: CurlWsFlag | int = CurlWsFlag.BINARY,
        timeout: float | None = None,
    ) -> None:
        """Send a WebSocket message.

        Args:
            payload: Data to send (``str``/``bytes``/``bytearray``/``memoryview``).
            flags: Frame type flags (e.g., ``CurlWsFlag.TEXT`` / ``CurlWsFlag.BINARY``).
            timeout: Max seconds to wait if the send queue is full.

        Raises:
            CurlError: Network related exception occured.
            WebSocketClosed: The WebSocket has been closed.
            WebSocketTimeout: The send operation timed out.

        Note:
            There are no limits on the size of the message that can be sent.
            Large outbound messages are seamlessly broken down into optimal
            fragments using the ``CURLWS_CONT`` flag, arriving as a single
            logical message to the server.

        Warning:
            This method is non-blocking. It queues the message for immediate
            transmission. Call ``await ws.flush()`` after sending if you need
            to guarantee that the data has actually reached the socket.
        """

        if self._transport_exception is not None:
            raise self._transport_exception

        if self.closed:
            raise WebSocketClosed("WebSocket is closed")

        # Fail fast when writer is done
        if self._write_task is not None and self._write_task.done():
            raise WebSocketClosed("WebSocket writer terminated; cannot send")

        # cURL expects bytes
        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        try:
            self._send_queue.put_nowait((payload, flags))
        except QueueFull as exc:
            if self._terminated:
                raise WebSocketClosed("WebSocket connection is terminated") from exc

            # Check exception after encoding
            if self._transport_exception is not None:
                raise self._transport_exception from exc

            if timeout is not None:
                try:
                    await wait_for(self._send_queue.put((payload, flags)), timeout)
                except AsyncTimeout as e:
                    raise WebSocketTimeout(
                        "Send queue full (network slow) - timed out enqueuing message",
                        code=CurlECode.OPERATION_TIMEDOUT,
                    ) from e
            else:
                await self._send_queue.put((payload, flags))

            # If we woke up because terminate() drained the queue, fail now.
            if self._transport_exception is not None:
                raise self._transport_exception from exc

            if self.closed or self._terminated:
                raise WebSocketClosed(
                    "Connection was terminated while waiting to send"
                ) from exc

    async def send_binary(
        self, payload: bytes, *, timeout: float | None = None
    ) -> None:
        """Send a binary frame.

        Args:
            payload: Binary data to send.
            timeout: Max seconds to wait if the send queue is full.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.BINARY, timeout=timeout)

    async def send_bytes(self, payload: bytes, *, timeout: float | None = None) -> None:
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: Binary data to send.
            timeout: Max seconds to wait if the send queue is full.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.BINARY, timeout=timeout)

    async def send_str(self, payload: str, *, timeout: float | None = None) -> None:
        """Send a text frame.

        Args:
            payload: Text data to send.
            timeout: Max seconds to wait if the send queue is full.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(payload, CurlWsFlag.TEXT, timeout=timeout)

    async def send_json(
        self,
        payload: object,
        *,
        dumps: Callable[..., str] = json_dumps,
        timeout: float | None = None,
    ) -> None:
        """Send a JSON frame.

        Args:
            payload: Data to send.
            dumps: JSON encoder, default is :meth:`json.dumps()`.
            timeout: Max seconds to wait if the send queue is full.

        For more info, see the docstring for :meth:`send()`
        """
        if dumps is json_dumps:
            return await self.send_str(
                json_dumps(payload, separators=(",", ":")), timeout=timeout
            )
        return await self.send_str(dumps(payload), timeout=timeout)

    async def ping(self, payload: str | bytes, *, timeout: float | None = None) -> None:
        """Send a ping frame.

        Args:
            payload: Data to send.
            timeout: Max seconds to wait if the send queue is full.

        Raises:
            WebSocketError: The payload length is outside specification.

        For more info, see the docstring for :meth:`send()`
        """
        return await self.send(
            self._prepare_ping_payload(payload), CurlWsFlag.PING, timeout=timeout
        )

    async def close(
        self,
        code: int | WsCloseCode = WsCloseCode.OK,
        message: str | bytes = b"",
        timeout: float = 3.0,
    ) -> None:
        """
        Performs a graceful WebSocket closing handshake and terminates the connection.

        This method sends a WebSocket close frame to the peer, waits for queued
        outgoing messages to be sent, and then shuts down the connection.

        Args:
            code (int): Close code. Defaults to ``WsCloseCode.OK``.
            message (bytes): Close reason. Defaults to ``b""``.
            timeout (float): How long (in seconds) to wait for the connection to close
                gracefully before force-terminating.
        """
        async with self._close_lock:
            if self.closed:
                return

            self.closed = True
            close_start: float = self.loop.time()

            if isinstance(message, str):
                message = message.encode("utf-8")

            # 125 bytes (Spec) - 2 bytes for close code
            max_msg_size: int = self._MAX_CONTROL_FRAME_SIZE - 2
            if len(message) > max_msg_size:
                message = message[:max_msg_size]

            # Store the code and reason
            if self._close_code is None:
                self._close_code = code
                self._close_reason = message.decode("utf-8", errors="replace")

            with suppress(AsyncTimeout, WebSocketError):
                if (
                    self._write_task
                    and not self._write_task.done()
                    and self._transport_exception is None
                ):
                    # Send Close Frame and wait for queue to empty
                    close_frame: bytes = self._pack_close_frame(code, message)
                    await wait_for(
                        self._send_queue.put((close_frame, CurlWsFlag.CLOSE)),
                        timeout=timeout,
                    )
                    # Subtract time already elapsed when flushing queue
                    await self.flush(
                        max(0.0, timeout - (self.loop.time() - close_start))
                    )

            # Ensure resources are cleaned up
            self.terminate()
            with suppress(AsyncTimeout):
                _ = await wait_for(
                    self._terminated_event.wait(),
                    max(0.0, timeout - (self.loop.time() - close_start)),
                )

    def terminate(self) -> None:  # pyright: ignore[reportImplicitOverride]
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

            loop: AbstractEventLoop | None = self._loop

            # Get the currently running event loop
            try:
                current_loop: AbstractEventLoop | None = get_running_loop()
            except RuntimeError:
                current_loop = None

            try:
                if loop is None:
                    raise RuntimeError("Event loop not available")

                # Run the termination task
                if current_loop is not None and current_loop is loop:
                    _ = loop.create_task(self._terminate_helper())
                else:
                    _ = run_coroutine_threadsafe(self._terminate_helper(), loop)

            # pylint: disable-next=broad-exception-caught
            except Exception:
                try:
                    super().terminate()
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
        queue_put_nowait: Callable[[RecvQueueItem], None] = (
            self._receive_queue.put_nowait
        )
        queue_put: Callable[[RecvQueueItem], Awaitable[None]] = self._receive_queue.put
        loop: AbstractEventLoop = self.loop
        loop_time: Callable[[], float] = loop.time
        create_future: Callable[[], Future[None]] = loop.create_future
        add_reader: Callable[..., None] = loop.add_reader
        remove_reader: Callable[..., bool] = loop.remove_reader
        time_slice: float = self._recv_time_slice
        next_yield: float = loop_time() + time_slice
        retry_on_error: bool = self.ws_retry.retry
        retry_codes: set[CurlECode] = self.ws_retry.codes
        max_retries: int = self.ws_retry.count
        retry_base: float = float(self.ws_retry.delay)
        e_again: int = int(CurlECode.AGAIN)
        e_recv_err: int = int(CurlECode.RECV_ERROR)
        e_nothing: int = int(CurlECode.GOT_NOTHING)
        close_flag: int = int(CurlWsFlag.CLOSE)
        cont_flag: int = int(CurlWsFlag.CONT)
        data_mask: int = CurlWsFlag.BINARY | CurlWsFlag.TEXT | cont_flag
        max_msg_size: int = self._max_message_size
        block_on_recv: bool = self._block_on_recv_queue_full
        queue_full_err: str = (
            "Receive queue full; failing connection to preserve message integrity"
        )
        set_fut_result: Callable[[Future[None]], None] = _safe_set_result

        # Message specific values
        recv_error_retries: int = 0
        chunks: list[bytes] = []
        msg_size: int = 0
        chunks_append: Callable[[bytes], None] = chunks.append
        chunks_clear: Callable[[], None] = chunks.clear

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
                        if (
                            "errno 11" in err_msg
                            or "resource temporarily unavailable" in err_msg
                        ):
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
                        read_future: Future[None] = create_future()
                        try:
                            add_reader(self._sock_fd, set_fut_result, read_future)
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
                                try:  # noqa: SIM105
                                    _ = remove_reader(self._sock_fd)
                                # pylint: disable-next=broad-exception-caught
                                except Exception:
                                    pass

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
                        await sleep(max(0.0, retry_delay))
                        continue

                    # Fatal error - can't retry
                    self._finalize_connection(e)
                    return

                flags: int = frame.flags
                if recv_error_retries > 0:
                    recv_error_retries = 0

                # Data Frames (Text / Binary / Cont)
                if flags & data_mask:
                    # Perform message size checks
                    msg_size += len(chunk)
                    if msg_size > max_msg_size:
                        chunks_clear()
                        self._finalize_connection(
                            WebSocketError(
                                (
                                    f"Message too large: {msg_size} bytes "
                                    f"(limit {max_msg_size} bytes). "
                                    "Consider increasing max_message_size or "
                                    "chunking the message."
                                ),
                                CurlECode.TOO_LARGE,
                            )
                        )
                        return

                    # Collect the chunk
                    chunks_append(chunk)

                    # If the message is complete, process and dispatch it
                    if not (flags & cont_flag or frame.bytesleft):
                        message: bytes = (
                            chunks[0] if len(chunks) == 1 else b"".join(chunks)
                        )
                        chunks_clear()
                        msg_size = 0

                        try:
                            queue_put_nowait((message, flags))
                        except QueueFull:
                            if not block_on_recv:
                                self._finalize_connection(
                                    WebSocketError(
                                        queue_full_err, CurlECode.OUT_OF_MEMORY
                                    )
                                )
                                return
                            await queue_put((message, flags))

                    if loop_time() >= next_yield:
                        await sleep(0)
                        next_yield = loop_time() + time_slice

                    continue

                # If a CLOSE frame is received, the reader is done.
                if flags & close_flag:
                    chunks_clear()
                    try:
                        queue_put_nowait((chunk, flags))
                    except QueueFull:
                        if not block_on_recv:
                            self._finalize_connection(
                                WebSocketError(queue_full_err, CurlECode.OUT_OF_MEMORY)
                            )
                            return

                        await queue_put((chunk, flags))
                    await self._handle_close_frame(chunk)
                    return

        except CancelledError:
            pass

        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            self._finalize_connection(e)

    async def _write_loop(self) -> None:
        """
        The background task responsible for consuming the send queue
        and transmitting frames.

        To maximize performance, this loop hoists the configuration
        check and enters one of two distinct processing strategies:

        1. Standard Mode (No Coalescing):
            The default, low-latency path. Messages are consumed one-by-one
            from the queue and transmitted immediately. This guarantees that one
            ``send()`` call results in exactly one WebSocket message, preserving
            logical message boundaries.

        2. Coalescing Mode:
            An optimized throughput path for chatty streams. The loop greedily gathers
            multiple pending messages from the queue (up to ``max_send_batch_size``
            and merges their payloads into a single transmission if they share the
            same flags (e.g., multiple text frames). This reduces system call
            overhead but does not preserve individual message boundaries.

        Features:
        - Cooperative Multitasking: Yields to the event loop periodically to prevent
            the writer from starving the reader task during high-volume transmission.
        - Control Frame Priority: PING and CLOSE frames are never coalesced; they
            trigger an immediate flush of any pending batched data before being sent.
        - Lifecycle Management: Automatically terminates the connection cleanly upon
            transmitting a CLOSE frame.
        """
        control_frame_flags: int = CurlWsFlag.CLOSE | CurlWsFlag.PING | CurlWsFlag.PONG
        close_flag: int = int(CurlWsFlag.CLOSE)
        send_payload: Callable[..., Awaitable[bool]] = self._send_payload
        queue_get: Callable[[], Awaitable[SendQueueItem]] = self._send_queue.get
        queue_get_nowait: Callable[[], SendQueueItem] = self._send_queue.get_nowait
        queue_done: Callable[[], None] = self._send_queue.task_done
        loop: AbstractEventLoop = self.loop
        loop_time: Callable[[], float] = loop.time
        time_slice: float = self._send_time_slice
        next_yield: float = loop_time() + time_slice

        try:
            # Hoist the branch - decide loop strategy once at start
            if not self._coalesce_frames:
                # Optimized fast path, no batching overhead
                while True:
                    payload, flags = await queue_get()

                    try:
                        if not await send_payload(payload, flags):
                            return

                        if flags & close_flag:
                            break

                        # Perform yield checks
                        if loop_time() >= next_yield:
                            await sleep(0)
                            next_yield = loop_time() + time_slice

                    finally:
                        queue_done()

            else:
                # Coalescing path: Batch multiple frames to merge payloads
                while True:
                    payload, flags = await queue_get()

                    # Build the rest of the batch without waiting.
                    batch: list[SendQueueItem] = [(payload, flags)]
                    if not (flags & close_flag):
                        while len(batch) < self._max_send_batch_size:
                            try:
                                payload, frame = queue_get_nowait()
                                batch.append((payload, frame))
                                if frame & close_flag:
                                    break

                            except QueueEmpty:
                                break

                    try:
                        # Group consecutive frames with same flags to preserve order.
                        # Control frames are strictly isolated and never coalesced.
                        coalesced: list[
                            tuple[list[bytes | bytearray | memoryview], int]
                        ] = []
                        for payload, frame in batch:
                            if frame & control_frame_flags:
                                coalesced.append(([payload], frame))
                            else:
                                if coalesced and coalesced[-1][1] == frame:
                                    coalesced[-1][0].append(payload)
                                else:
                                    coalesced.append(([payload], frame))

                        # Transmit the coalesced groups in their exact original order
                        for payloads, frame_group in coalesced:
                            if not await send_payload(b"".join(payloads), frame_group):
                                return

                            # Perform yield checks
                            if loop_time() >= next_yield:
                                await sleep(0)
                                next_yield = loop_time() + time_slice

                    finally:
                        # Mark all processed items as done.
                        for _ in range(len(batch)):
                            queue_done()

                    # Exit cleanly after sending a CLOSE frame.
                    if batch[-1][1] & close_flag:
                        break

        except CancelledError:
            pass

        # pylint: disable-next=broad-exception-caught
        except Exception as e:
            self._finalize_connection(e)

        finally:
            # If the loop exits unexpectedly, ensure we terminate the connection.
            if not self.closed:
                self.terminate()

    async def _send_payload(
        self, payload: bytes | memoryview | bytearray, flags: CurlWsFlag | int
    ) -> bool:
        """
        Optimized low-level sender with fragmentation logic.
        """
        # Cache locals to reduce lookup cost
        curl_ws_send: Callable[[memoryview, CurlWsFlag | int], int] = self.curl.ws_send
        loop: AbstractEventLoop = self.loop
        loop_time: Callable[[], float] = loop.time
        create_future: Callable[[], Future[None]] = loop.create_future
        add_writer: Callable[..., None] = loop.add_writer
        remove_writer: Callable[..., bool] = loop.remove_writer
        set_fut_result: Callable[[Future[None]], None] = _safe_set_result
        sock_fd: int = self._sock_fd
        time_slice: float = self._send_time_slice
        next_yield: float = loop_time() + time_slice
        max_frame_size: int = self._MAX_CURL_FRAME_SIZE
        e_again: int = int(CurlECode.AGAIN)
        e_send_err: int = int(CurlECode.SEND_ERROR)
        cont_flag: int = int(CurlWsFlag.CONT)
        max_zero_writes: int = 3

        # Message specific values
        base_flags: int = flags & ~cont_flag
        view: memoryview = memoryview(payload)
        total_bytes: int = view.nbytes
        offset: int = 0
        write_retries: int = 0
        frame_end: int = 0
        current_flags: CurlWsFlag | int = flags

        # Loop until the entire view is sent
        while offset < total_bytes or (offset == 0 and total_bytes == 0):
            # Boundary check: Calculate next fragment ONLY when needed
            if offset == frame_end:
                if total_bytes - offset > max_frame_size:
                    frame_end = offset + max_frame_size
                    current_flags = base_flags | cont_flag
                else:
                    frame_end = total_bytes
                    current_flags = flags

            try:
                # libcurl returns the number of bytes actually sent
                n_sent: int = curl_ws_send(view[offset:frame_end], current_flags)

                if n_sent == 0:
                    # Handle 0-byte payload (Valid Empty Frame)
                    if frame_end - offset == 0:
                        return True

                    # Raise AGAIN to jump to the existing wait logic below
                    write_retries += 1
                    if write_retries >= max_zero_writes:
                        self._finalize_connection(
                            WebSocketError(
                                f"Writer stalled ({write_retries} attempts).",
                                CurlECode.WRITE_ERROR,
                            )
                        )
                        return False

                    raise CurlError("0 bytes sent", e_again)

                if write_retries:
                    write_retries = 0

                offset += n_sent

                # Cooperative yield checks
                if loop_time() >= next_yield:
                    await sleep(0)
                    next_yield = loop_time() + time_slice

            except CurlError as e:
                code: int = e.code
                retry_eagain: bool = False

                # Handle normal cURL EAGAINs
                if code == e_again:
                    retry_eagain = True

                # EAGAIN ("errno 11") bubbling up as SEND_ERROR from BoringSSL
                elif code == e_send_err:
                    err_msg: str = str(e).lower()
                    if (
                        "errno 11" in err_msg
                        or "resource temporarily unavailable" in err_msg
                    ):
                        retry_eagain = True

                if retry_eagain:
                    # Wait for socket to be writable
                    write_future: Future[None] = create_future()
                    try:
                        add_writer(sock_fd, set_fut_result, write_future)
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
                            try:  # noqa: SIM105
                                _ = remove_writer(sock_fd)
                            # pylint: disable-next=broad-exception-caught
                            except Exception:
                                pass

                    # Retry the exact same chunk
                    continue

                # Fatal Error
                self._finalize_connection(e)
                return False

        return True

    async def recv_fragment(
        self, *, timeout: float | None = None
    ) -> tuple[bytes, CurlWsFrame]:
        """This function is deprecated and removed.
        The new architecture automatically handles frame reassembly.
        Call :meth:`recv()` instead as a direct replacement.
        """
        _ = timeout
        raise NotImplementedError(
            "recv_fragment() is no longer supported. "
            + "Call recv() instead to get complete messages. "
            + "See docs: https://curl-cffi.readthedocs.io/en/latest/websockets.html"
        )

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
        if self._write_task is None:
            return

        # Create a task for the queue join operation
        join_task: Task[None] = create_task(self._send_queue.join())

        try:
            done, _ = await wait(
                {join_task, self._write_task},
                return_when=FIRST_COMPLETED,
                timeout=timeout,
            )

            if not done:
                raise WebSocketTimeout(
                    "Timed out waiting for send queue to flush.",
                    CurlECode.OPERATION_TIMEDOUT,
                )

            # Fast path: queue drained
            if join_task in done:
                return

            # Writer finished first
            if self._write_task in done:
                try:
                    self._write_task.result()
                except Exception as exc:
                    raise WebSocketError("Writer task crashed while flushing.") from exc

                # If the writer finished gracefully
                if self._send_queue.empty():
                    return

                # Expose the actual network error that killed the writer
                if self._transport_exception is not None:
                    raise self._transport_exception

                raise WebSocketError("Writer task stopped unexpectedly while flushing.")

        finally:
            # Cancel join task on early exit to avoid leak.
            if not join_task.done():
                _ = join_task.cancel()
                with suppress(CancelledError):
                    await join_task

    async def _terminate_helper(self) -> None:
        """Utility method for connection termination"""
        tasks_to_cancel: set[Task[None]] = {
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
                _, pending = await wait(
                    tasks_to_cancel,
                    timeout=max_timeout,
                    return_when=ALL_COMPLETED,
                )
                # Force cancel tasks that didn't complete within timeout.
                for p in pending:
                    _ = p.cancel()

            # Drain the send_queue
            while not self._send_queue.empty():
                try:
                    _ = self._send_queue.get_nowait()
                    self._send_queue.task_done()
                except (QueueEmpty, ValueError):
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
            if (
                self.session
                # pylint: disable-next=protected-access
                and not self.session._closed  # pyright: ignore[reportPrivateUsage]
            ):
                # WebSocket curls CANNOT be reused
                self.session.push_curl(None)

        finally:
            self._terminated_event.set()


@final
class AsyncWebSocketContext:
    """Helper to enable simpler context manager usage"""

    __slots__ = ("_coro", "_obj")

    def __init__(self, coro: Awaitable[AsyncWebSocket]) -> None:
        self._coro: Awaitable[AsyncWebSocket] = coro
        self._obj: AsyncWebSocket | None = None

    def __await__(self) -> Generator[object, object, AsyncWebSocket]:
        return self._coro.__await__()

    async def __aenter__(self) -> AsyncWebSocket:
        self._obj = await self._coro
        return self._obj

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: object | None,
    ) -> None:
        if self._obj:
            if exc_type is None:
                await self._obj.close()
            else:
                with suppress(CurlError):
                    await self._obj.close()
