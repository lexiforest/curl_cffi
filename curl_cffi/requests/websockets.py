from __future__ import annotations

import asyncio
import struct
import warnings
from enum import IntEnum
from functools import partial
from json import dumps, loads
from select import select
from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, TypeVar, Union

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

    def __init__(self, message: str, code: Union[WsCloseCode, CurlECode, Literal[0]] = 0):
        super().__init__(message, code)  # type: ignore


class WebSocketClosed(WebSocketError, SessionClosed):
    """WebSocket is already closed."""


class WebSocketTimeout(WebSocketError, Timeout):
    """WebSocket operation timed out."""


async def aselect(
    fd,
    mode: Literal["read", "write"] = "read",
    *,
    loop: asyncio.AbstractEventLoop,
    timeout: Optional[float] = None,
) -> bool:
    future = loop.create_future()

    if mode == "read":
        loop.add_reader(fd, future.set_result, None)
        future.add_done_callback(lambda _: loop.remove_reader(fd))
    elif mode == "write":
        loop.add_writer(fd, future.set_result, None)
        future.add_done_callback(lambda _: loop.remove_writer(fd))
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'read' or 'write'")

    try:
        await asyncio.wait_for(future, timeout)
    except asyncio.TimeoutError:
        return False
    return True


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
                raise WebSocketError("Invalid close message", WsCloseCode.INVALID_DATA) from e
            except Exception as e:
                raise WebSocketError("Invalid close frame", WsCloseCode.PROTOCOL_ERROR) from e
            else:
                if code not in WsCloseCode._value2member_map_ or code == WsCloseCode.UNKNOWN:
                    raise WebSocketError(f"Invalid close code: {code}", WsCloseCode.PROTOCOL_ERROR)
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
            raise WebSocketError("Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE)

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

    def send(self, payload: Union[str, bytes], flags: CurlWsFlag = CurlWsFlag.BINARY):
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
            raise WebSocketError("Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE)

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
            raise WebSocketError("Invalid active socket", CurlECode.NO_CONNECTION_AVAILABLE)

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
                            raise WebSocketError("Invalid UTF-8", WsCloseCode.INVALID_DATA) from e

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
    """An async WebSocket implementation using libcurl."""

    def __init__(
        self,
        session: AsyncSession,
        curl: Curl,
        *,
        autoclose: bool = True,
        debug: bool = False,
    ):
        super().__init__(curl=curl, autoclose=autoclose, debug=debug)
        self.session: AsyncSession = session
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._receive_queue: asyncio.Queue = asyncio.Queue(maxsize=4096)
        self._send_lock = asyncio.Lock()
        self._io_task: Optional[asyncio.Task[None]] = None
        self._sock_fd: int = -1

    @property
    def loop(self):
        if self._loop is None:
            self._loop = get_selector(asyncio.get_running_loop())
        return self._loop

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, _exc_type, _exc_val, _exc_tb) -> None:
        await self.close()

    def __aiter__(self) -> Self:
        if self.closed:
            raise WebSocketClosed("WebSocket has been closed")
        if self._io_task is None:
            self._start_io()
        return self

    async def __anext__(self) -> bytes:
        message, flags = await self.recv()
        if flags & CurlWsFlag.CLOSE:
            raise StopAsyncIteration
        if message is None:
            raise StopAsyncIteration
        return message

    def _start_io(self):
        """Initializes the socket and starts the persistent I/O tasks."""
        if self._io_task is not None:
            return

        self._sock_fd = self.curl.getinfo(CurlInfo.ACTIVESOCKET)
        if self._sock_fd == CURL_SOCKET_BAD:
            raise WebSocketError(
                "Invalid active socket. Connection may have failed.",
                code=CurlECode.NO_CONNECTION_AVAILABLE,
            )

        self._io_task = self.loop.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        """
        The core I/O task. It actively drains the read buffer and waits for
        read-readiness on-demand, correctly handling backpressure without
        busy-waiting.
        """
        buffer: bytearray = bytearray()

        # This is a tunable parameter. It represents the maximum duration the loop
        # can run without yielding. 1ms is a reasonable default.
        YIELD_INTERVAL_S = 0.001

        try:
            while not self.closed:
                # Try to read and process as much data as is available in the
                # socket buffer without waiting. This is the "greedy" part.

                # Record the start time before entering the greedy loop
                start_time = self.loop.time()

                while not self.closed:
                    try:
                        chunk, frame = self._curl.ws_recv()
                        buffer.extend(chunk)

                        if frame.bytesleft == 0 and not (frame.flags & CurlWsFlag.CONT):
                            message, flags = bytes(buffer), frame.flags
                            buffer.clear()
                            await self._receive_queue.put((message, flags))

                            if flags & CurlWsFlag.CLOSE:
                                self._handle_close_frame(message)
                                return

                            # THE FIX IS HERE: Check if the timeslice is exhausted
                            if self.loop.time() - start_time > YIELD_INTERVAL_S:
                                await asyncio.sleep(0)  # Yield control
                                start_time = self.loop.time()  # Reset the timer

                    except CurlError as e:
                        # The OS socket buffer is empty. Break the inner loop.
                        if e.code == CurlECode.AGAIN:
                            break

                        # An actual error occurred.
                        await self._receive_queue.put((e, 0))
                        return

                # The buffer was drained (EAGAIN was hit).
                # We must now wait cooperatively for more data to arrive.
                read_ready_future = self.loop.create_future()
                self.loop.add_reader(self._sock_fd, read_ready_future.set_result, None)
                try:
                    # Wait until the event loop signals the socket is readable again.
                    await read_ready_future
                finally:
                    # Remove the temporary reader registration
                    self.loop.remove_reader(self._sock_fd)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            if not self.closed:
                await self._receive_queue.put((e, 0))
        finally:
            if not self.closed:
                await self.close(WsCloseCode.ABNORMAL_CLOSURE)

    def _handle_close_frame(self, message: bytes):
        """Processes a received CLOSE frame."""
        try:
            self._close_code, self._close_reason = self._unpack_close_frame(message)
        except WebSocketError as e:
            self._close_code = e.code
        finally:
            if self.autoclose and not self.closed:
                self.loop.create_task(self.close(self._close_code or WsCloseCode.OK))

    async def recv(self, *, timeout: Optional[float] = None) -> tuple[Optional[bytes], int]:
        """Receives a single message from the WebSocket."""
        if self.closed and self._receive_queue.empty():
            raise WebSocketClosed("WebSocket is closed")

        if self._io_task is None:
            self._start_io()

        try:
            future = self._receive_queue.get()
            result, flags = await asyncio.wait_for(future, timeout)
            if isinstance(result, Exception):
                raise result
            return result, flags
        except asyncio.TimeoutError as e:
            raise WebSocketTimeout("WebSocket recv() timed out") from e

    async def recv_str(self, *, timeout: Optional[float] = None) -> str:
        data, flags = await self.recv(timeout=timeout)
        if data is None or not (flags & CurlWsFlag.TEXT):
            raise WebSocketError("Not a valid text frame", WsCloseCode.INVALID_DATA)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as e:
            raise WebSocketError("Invalid UTF-8 in text frame", WsCloseCode.INVALID_DATA) from e

    async def recv_json(
        self, *, loads: Callable[[Union[str, bytes]], T] = loads, timeout: Optional[float] = None
    ) -> T:
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
            except Exception:
                return loads(data)
        elif flags & CurlWsFlag.BINARY:
            return loads(data)
        else:
            raise WebSocketError(
                "Not a valid text or binary frame for JSON", WsCloseCode.INVALID_DATA
            )

    async def send(self, payload: Union[str, bytes], flags: CurlWsFlag = CurlWsFlag.BINARY):
        """
        Sends data asynchronously, correctly handling backpressure and cooperatively
        yielding to the event loop when sending large payloads.
        """
        if self.closed:
            raise WebSocketClosed("WebSocket is closed")

        if self._io_task is None:
            self._start_io()

        if isinstance(payload, str):
            payload = payload.encode("utf-8")

        view = memoryview(payload)
        # This is a tunable parameter, representing the maximum duration the loop
        # can run without yielding. 1ms is a reasonable default.
        YIELD_INTERVAL_S = 0.001

        async with self._send_lock:
            offset = 0
            payload_len = len(payload)
            start_time = self.loop.time()
            while offset < payload_len:
                try:
                    n_sent = self._curl.ws_send(view[offset:], flags)
                    offset += n_sent

                    # THE FIX IS HERE: Check if the timeslice is exhausted and yield control
                    if self.loop.time() - start_time > YIELD_INTERVAL_S:
                        await asyncio.sleep(0)
                        start_time = self.loop.time()  # Reset the timer for the new timeslice

                except CurlError as e:
                    if e.code == CurlECode.AGAIN:
                        # The OS socket buffer is full. We must wait cooperatively.
                        future = self.loop.create_future()
                        self.loop.add_writer(self._sock_fd, future.set_result, None)
                        try:
                            await future
                        finally:
                            self.loop.remove_writer(self._sock_fd)

                        # After waiting for the socket to be ready, reset the timeslice timer
                        start_time = self.loop.time()
                        continue

                    raise WebSocketError(f"Failed to send data: {e.message}", e.code) from e

    async def send_binary(self, payload: bytes):
        """Send a binary frame.

        Args:
            payload: binary data to send.
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_bytes(self, payload: bytes):
        """Send a binary frame, alias of :meth:`send_binary`.

        Args:
            payload: binary data to send.
        """
        return await self.send(payload, CurlWsFlag.BINARY)

    async def send_str(self, payload: str):
        """Send a text frame.

        Args:
            payload: text data to send.
        """
        return await self.send(payload, CurlWsFlag.TEXT)

    async def send_json(self, payload: Any, *, dumps: Callable[[Any], str] = dumps):
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

    async def close(self, code: int = WsCloseCode.OK, message: bytes = b""):
        if self.closed:
            return

        self.closed = True
        try:
            close_frame = self._pack_close_frame(code, message)
            # Use a short timeout to prevent close from blocking forever on a dead socket
            await asyncio.wait_for(self.send(close_frame, CurlWsFlag.CLOSE), timeout=5.0)
        except (WebSocketError, WebSocketClosed, asyncio.TimeoutError):
            pass
        finally:
            self.terminate()
            if self._io_task:
                await asyncio.sleep(0)
                self._io_task = None

    def terminate(self):
        """Forcibly terminates the connection and cleans up all resources."""
        if self._io_task and not self._io_task.done():
            self._io_task.cancel()

        if self._sock_fd != -1:
            # Use try/except in case the writer was already removed or never added
            try:
                self.loop.remove_reader(self._sock_fd)
            except (ValueError, OSError):
                pass
            try:
                # --- MODIFIED --- This is just for safety, but we shouldn't have a permanent writer.
                self.loop.remove_writer(self._sock_fd)
            except (ValueError, OSError):
                pass
            self._sock_fd = -1

        # Terminate the underlying connection.
        super().terminate()
        if not self.session._closed:
            # WebSocket curls CANNOT be reused
            self.session.push_curl(None)

    @staticmethod
    def _pack_close_frame(code: int, reason: bytes) -> bytes:
        return struct.pack("!H", code) + reason

    @staticmethod
    def _unpack_close_frame(frame: bytes) -> tuple[int, str]:
        if len(frame) < 2:
            return WsCloseCode.ABNORMAL_CLOSURE, ""
        try:
            code = struct.unpack_from("!H", frame)[0]
            reason = frame[2:].decode("utf-8")
        except (struct.error, UnicodeDecodeError):
            raise WebSocketError("Invalid close frame", WsCloseCode.PROTOCOL_ERROR)

        if not (1000 <= code <= 1015 or 3000 <= code <= 4999):
            raise WebSocketError(f"Invalid close code: {code}", WsCloseCode.PROTOCOL_ERROR)
        return code, reason
