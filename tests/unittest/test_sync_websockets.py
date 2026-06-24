"""
Comprehensive test suite for the Synchronous WebSocket implementation.

This module provides reusable, composable test infrastructure for testing
the WebSocket class across various scenarios including:
- Basic connectivity and message exchange
- Different message types (binary, text, JSON)
- Timeout behavior and socket stalls
- Error propagation and handling
- Large message fragmentation and SIMD boundaries
- Callback-driven run_forever() architecture
- Connection lifecycle management
- Thread-safety of the C-layer SIMD state
- High volume performance checks
- Strict Protocol Spec Compliance
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import queue
import threading
import time
import unittest.mock
from collections.abc import Awaitable, Callable, Generator, Iterator
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Literal
from unittest.mock import Mock

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from curl_cffi import (
    Curl,
    CurlECode,
    CurlError,
    CurlWsFlag,
    Response,
    Session,
    WebSocket,
    WebSocketClosed,
    WebSocketError,
    WebSocketRetryStrategy,
    WebSocketTimeout,
    WsCloseCode,
)


class ServerBehavior(Enum):
    ECHO = auto()
    BROADCAST = auto()
    CLOSE_IMMEDIATELY = auto()
    CLOSE_AFTER_N = auto()
    SILENT = auto()
    LARGE_RESPONSE = auto()
    SEND_PINGS = auto()


@dataclass
class ServerConfig:
    behavior: ServerBehavior = ServerBehavior.ECHO
    delay_seconds: float = 0.0
    close_after_n: int = 1
    broadcast_messages: list[bytes | str] = field(default_factory=list)
    response_size: int = 1024
    close_code: int = WsCloseCode.OK
    close_reason: str = ""
    max_size: int = 32 * 1024 * 1024


async def echo_handler(ws: websockets.ServerConnection, config: ServerConfig) -> None:
    try:
        async for msg in ws:
            if config.delay_seconds > 0:
                await asyncio.sleep(config.delay_seconds)
            await ws.send(msg)
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def broadcast_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    try:
        for msg in config.broadcast_messages:
            await ws.send(msg)
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def send_pings_handler(
    ws: websockets.ServerConnection, _config: ServerConfig
) -> None:
    try:
        _ = await ws.ping(b"server_ping_1")
        await asyncio.sleep(0.05)
        await ws.send(b"data_1")
        _ = await ws.ping(b"server_ping_2")
        await asyncio.sleep(0.05)
        await ws.send(b"data_2")
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def close_immediately_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    await ws.close(config.close_code, config.close_reason)


async def close_after_n_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    try:
        count = 0
        async for msg in ws:
            await ws.send(msg)
            count += 1
            if count >= config.close_after_n:
                await ws.close(config.close_code, config.close_reason)
                return
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def silent_handler(
    ws: websockets.ServerConnection, _config: ServerConfig
) -> None:
    try:
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def large_response_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    try:
        async for _ in ws:
            await ws.send(b"X" * config.response_size)
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


HANDLERS: dict[ServerBehavior, Callable[..., Awaitable[None]]] = {
    ServerBehavior.ECHO: echo_handler,
    ServerBehavior.BROADCAST: broadcast_handler,
    ServerBehavior.CLOSE_IMMEDIATELY: close_immediately_handler,
    ServerBehavior.CLOSE_AFTER_N: close_after_n_handler,
    ServerBehavior.SILENT: silent_handler,
    ServerBehavior.LARGE_RESPONSE: large_response_handler,
    ServerBehavior.SEND_PINGS: send_pings_handler,
}


@dataclass
class ConfigurableWSServer:
    url: str
    port: int
    stop: Callable[[], None]
    set_config: Callable[[ServerConfig], None]
    _thread: threading.Thread

    def configure(self, **kwargs) -> None:
        self.set_config(ServerConfig(**kwargs))


def start_configurable_ws_server(port: int) -> ConfigurableWSServer:
    ready: threading.Event = threading.Event()
    stop_q: queue.Queue[Callable[[], None]] = queue.Queue()
    config_holder: list[ServerConfig] = [ServerConfig()]

    def set_config(cfg: ServerConfig) -> None:
        config_holder[0] = cfg

    def _thread_target() -> None:
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        stop_event: asyncio.Event = asyncio.Event()

        def _stop() -> None:
            _ = loop.call_soon_threadsafe(stop_event.set)

        async def handler(ws: websockets.ServerConnection) -> None:
            cfg: ServerConfig = config_holder[0]
            handler_fn: Callable[..., Awaitable[None]] = HANDLERS.get(
                cfg.behavior, echo_handler
            )
            await handler_fn(ws, cfg)

        async def _run() -> None:
            initial_max_size: int = config_holder[0].max_size
            async with websockets.serve(
                handler, "127.0.0.1", port, max_size=initial_max_size
            ):
                stop_q.put(_stop)
                ready.set()
                _ = await stop_event.wait()

        try:
            loop.run_until_complete(_run())
        finally:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

    t: threading.Thread = threading.Thread(target=_thread_target, daemon=True)
    t.start()

    stop: Callable[[], None] = stop_q.get()
    _ = ready.wait()

    return ConfigurableWSServer(
        url=f"ws://127.0.0.1:{port}",
        port=port,
        stop=stop,
        set_config=set_config,
        _thread=t,
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def configurable_ws_server() -> Generator[ConfigurableWSServer, None, None]:
    server: ConfigurableWSServer = start_configurable_ws_server(port=8966)
    try:
        yield server
    finally:
        server.stop()
        server._thread.join(timeout=5)


@pytest.fixture
def ws_config(configurable_ws_server: ConfigurableWSServer) -> Callable[..., None]:
    configurable_ws_server.set_config(ServerConfig())

    def configure(**kwargs) -> None:
        configurable_ws_server.set_config(ServerConfig(**kwargs))

    return configure


@pytest.fixture
def session() -> Iterator[Session]:
    with Session[Response]() as s:
        yield s


@pytest.fixture
def ws_connection(
    session: Session,
    configurable_ws_server: ConfigurableWSServer,
    ws_config: Callable[..., None],
) -> Iterator[WebSocket]:
    ws_config()
    with session.ws_connect(configurable_ws_server.url) as ws:
        yield ws


# =============================================================================
# Test Classes
# =============================================================================


class TestWebSocketBasicConnectivity:
    def test_connect_and_close(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        ws: WebSocket = session.ws_connect(configurable_ws_server.url)
        assert not ws.closed
        ws.close()
        assert ws.closed

    def test_context_manager(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        with session.ws_connect(configurable_ws_server.url) as ws:
            assert not ws.closed
        assert ws.closed

    def test_echo_single_message(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send(b"hello", timeout=5.0)
        data, flags = ws_connection.recv(timeout=5.0)
        assert data == b"hello"
        assert flags & CurlWsFlag.BINARY

    def test_echo_multiple_messages(self, ws_connection: WebSocket) -> None:
        for i in range(10):
            msg: str = f"message_{i}"
            _ = ws_connection.send_str(msg, timeout=5.0)
            response: str = ws_connection.recv_str(timeout=5.0)
            assert response == msg

    def test_invalid_socket_handle(self) -> None:
        """Verifies that an uninitialized or broken libcurl socket throws correctly."""
        mock_curl: Mock = Mock(spec=Curl)
        mock_curl.getinfo.return_value = -1
        ws: WebSocket = WebSocket(curl=mock_curl)
        with pytest.raises(WebSocketError) as exc:
            _ = ws._get_sock_fd()
        assert exc.value.code == CurlECode.NO_CONNECTION_AVAILABLE


class TestWebSocketMessageTypes:
    def test_send_recv_binary(self, ws_connection: WebSocket) -> None:
        payload = b"\x00\x01\x02\xff\xfe"
        _ = ws_connection.send_binary(payload, timeout=5.0)
        data, flags = ws_connection.recv(timeout=5.0)
        assert data == payload
        assert flags & CurlWsFlag.BINARY

    def test_send_recv_text(self, ws_connection: WebSocket) -> None:
        payload = "Hello, WebSocket! 你好 🎉"
        _ = ws_connection.send_str(payload, timeout=5.0)
        response: str = ws_connection.recv_str(timeout=5.0)
        assert response == payload

    def test_send_recv_json(self, ws_connection: WebSocket) -> None:
        payload: dict[str, str | int | dict[str, int]] = {
            "key": "value",
            "number": 42,
            "nested": {"a": 1},
        }
        _ = ws_connection.send_json(payload, timeout=5.0)
        assert ws_connection.recv_json(timeout=5.0) == payload

    def test_send_bytearray(self, ws_connection: WebSocket) -> None:
        payload: bytearray = bytearray(b"bytearray_test")
        _ = ws_connection.send(payload, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == bytes(payload)

    def test_send_memoryview(self, ws_connection: WebSocket) -> None:
        original = b"memoryview_test"
        payload: memoryview = memoryview(original)
        _ = ws_connection.send(payload, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == original

    def test_recv_str_invalid_utf8(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send(b"\xff\xfe", timeout=5.0)
        with pytest.raises(WebSocketError) as exc_info:
            ws_connection.recv_str(timeout=5.0)
        assert exc_info.value.code == WsCloseCode.INVALID_DATA

    def test_recv_json_invalid(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send_str("not valid json {", timeout=5.0)
        with pytest.raises(WebSocketError) as exc_info:
            ws_connection.recv_json(timeout=5.0)
        assert exc_info.value.code == WsCloseCode.INVALID_DATA

    def test_server_ping_is_silently_consumed(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.SEND_PINGS)
        with session.ws_connect(configurable_ws_server.url) as ws:
            data1, flags1 = ws.recv(timeout=2.0)
            assert data1 == b"data_1"
            assert not (flags1 & CurlWsFlag.PING)

            data2, flags2 = ws.recv(timeout=2.0)
            assert data2 == b"data_2"
            assert not (flags2 & CurlWsFlag.PING)

            with pytest.raises(WebSocketTimeout):
                _ = ws.recv(timeout=0.2)

    def test_pong_is_silently_consumed(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.SILENT)
        with session.ws_connect(configurable_ws_server.url) as ws:
            _ = ws.ping(b"heartbeat", timeout=2.0)
            # The server will send a PONG. The sync hot-loop must discard it.
            with pytest.raises(WebSocketTimeout):
                _ = ws.recv(timeout=0.5)


class TestWebSocketTimeouts:
    def test_recv_timeout(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.SILENT)
        with session.ws_connect(configurable_ws_server.url) as ws:
            _ = ws.send(b"hello", timeout=2.0)
            with pytest.raises(WebSocketTimeout):
                ws.recv(timeout=0.2)

    def test_recv_timeout_returns_early(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send_str("quick", timeout=2.0)
        response: str = ws_connection.recv_str(timeout=5.0)
        assert response == "quick"

    def test_send_timeout_during_eagain_loop(self) -> None:
        """Proves that a timeout properly fires even if stuck mid-EAGAIN loop."""
        mock_curl: Mock = Mock(spec=Curl)
        ws: WebSocket = WebSocket(curl=mock_curl)
        ws.closed = False
        ws._sock_fd = 999
        mock_selector: Mock = Mock()
        ws._read_selector = mock_selector
        ws._write_selector = mock_selector

        # Raise EAGAIN every time
        mock_curl.ws_send.side_effect = CurlError("EAGAIN", CurlECode.AGAIN)

        # Let select mock simulate time passing beyond the timeout
        def mock_select(timeout) -> Literal[False]:
            time.sleep(0.06)  # Force clock advance past the 0.05 deadline
            return False

        mock_selector.select.side_effect = mock_select

        with pytest.raises(WebSocketTimeout):
            ws.send(b"data", timeout=0.05)


class TestWebSocketEdgeCases:
    def test_empty_message(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send(b"", timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == b""

    def test_empty_string_message(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.send_str("", timeout=5.0)
        response: str = ws_connection.recv_str(timeout=5.0)
        assert response == ""

    def test_unicode_edge_cases(self, ws_connection: WebSocket) -> None:
        test_strings: list[str] = [
            "",
            "a",
            "🎉",
            "Hello 世界 🌍",
            "\u0000",
            "a" * 10000,
        ]
        for s in test_strings:
            _ = ws_connection.send_str(s, timeout=5.0)
            response: str = ws_connection.recv_str(timeout=5.0)
            assert response == s

    def test_binary_all_byte_values(self, ws_connection: WebSocket) -> None:
        payload: bytes = bytes(range(256))
        _ = ws_connection.send(payload, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == payload

    def test_rapid_send_recv(self, ws_connection: WebSocket) -> None:
        for i in range(100):
            msg: str = f"rapid_{i}"
            _ = ws_connection.send_str(msg, timeout=2.0)
            response: str = ws_connection.recv_str(timeout=2.0)
            assert response == msg


class TestWebSocketPing:
    def test_ping_valid_payload(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.ping(b"heartbeat", timeout=2.0)
        assert not ws_connection.closed

    def test_ping_empty_payload(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.ping(b"", timeout=2.0)
        assert not ws_connection.closed

    def test_ping_max_size(self, ws_connection: WebSocket) -> None:
        _ = ws_connection.ping(b"X" * 125, timeout=2.0)
        assert not ws_connection.closed

    def test_ping_too_large_raises(self, ws_connection: WebSocket) -> None:
        with pytest.raises(WebSocketError):
            _ = ws_connection.ping(b"X" * 126, timeout=2.0)


class TestWebSocketLargeMessages:
    @pytest.mark.parametrize("size", [1024, 65536, 100_000, 500_000])
    def test_large_message_echo(self, ws_connection: WebSocket, size: int) -> None:
        payload: bytes = b"X" * size
        _ = ws_connection.send(payload, timeout=10.0)
        data, _ = ws_connection.recv(timeout=10.0)
        assert len(data) == size
        assert data == payload

    def test_message_at_curl_frame_boundary(self, ws_connection: WebSocket) -> None:
        payload: bytes = b"B" * 65536
        _ = ws_connection.send(payload, timeout=10.0)
        data, _ = ws_connection.recv(timeout=10.0)
        assert data == payload


class TestWebSocketRunForever:
    def test_run_forever_echo(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.ECHO)

        received: list[bytes | str] = []
        messages_to_send: list[bytes] = [b"alpha", b"beta", b"gamma"]

        def on_open(ws: WebSocket) -> None:
            for m in messages_to_send:
                _ = ws.send(m, timeout=2.0)

        def on_message(ws: WebSocket, msg: bytes | str) -> None:
            received.append(msg)
            if len(received) == 3:
                ws.close()

        with session.ws_connect(
            configurable_ws_server.url, on_open=on_open, on_message=on_message
        ) as ws:
            ws.run_forever()

        assert len(received) == 3
        assert received == messages_to_send

    def test_run_forever_server_closes(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.CLOSE_AFTER_N, close_after_n=1)

        close_code: int | None = None

        def on_open(ws: WebSocket) -> None:
            _ = ws.send(b"trigger", timeout=2.0)

        def on_close(ws: WebSocket, code: int, reason: str) -> None:
            nonlocal close_code
            close_code = code

        with session.ws_connect(
            configurable_ws_server.url, on_open=on_open, on_close=on_close
        ) as ws:
            ws.run_forever()

        assert close_code == WsCloseCode.OK

    def test_run_forever_enforces_max_message_size(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Verifies that run_forever() enforces the max_message_size restriction,
        gracefully closes the socket, and triggers the on_error callback.
        """
        two_mb = 2 * 1024 * 1024
        ws_config(behavior=ServerBehavior.LARGE_RESPONSE, response_size=two_mb)

        error_triggered = False
        close_code: int | None = None

        def on_open(ws: WebSocket) -> None:
            _ = ws.send(b"trigger", timeout=2.0)

        def on_error(ws: WebSocket, exc: Exception) -> None:
            nonlocal error_triggered
            error_triggered = True
            assert isinstance(exc, WebSocketError)
            assert "too large" in str(exc).lower()

        def on_close(ws: WebSocket, code: int, reason: str) -> None:
            nonlocal close_code
            close_code = code

        with (
            session.ws_connect(
                configurable_ws_server.url,
                max_message_size=1024 * 1024,  # Client limit is 1MB
                on_open=on_open,
                on_error=on_error,
                on_close=on_close,
            ) as ws,
            pytest.raises(WebSocketError),
        ):
            ws.run_forever()

        assert error_triggered
        assert close_code == WsCloseCode.MESSAGE_TOO_BIG

    def test_run_forever_invalid_utf8_closes(self) -> None:
        """Ensures bad UTF-8 data correctly triggers a protocol drop."""
        mock_curl: Mock = Mock(spec=Curl)
        ws: WebSocket = WebSocket(curl=mock_curl, skip_utf8_validation=False)
        ws.closed = False
        ws._sock_fd = 999
        ws._read_selector = Mock()
        ws._write_selector = Mock()

        class MockFrameMeta:
            def __init__(self) -> None:
                self.flags = CurlWsFlag.TEXT
                self.bytesleft = 0

        # Simulate receiving invalid utf8
        mock_curl.ws_recv.return_value = (b"\xff\xfe", MockFrameMeta())
        mock_curl.ws_send.return_value = 0  # Dummy mock for the auto-close call

        close_called = False

        def on_close(w, code, reason) -> None:
            nonlocal close_called
            close_called = True
            assert code == WsCloseCode.INVALID_DATA

        ws._emitters["close"] = on_close
        ws._emitters["message"] = lambda w, m: None

        with pytest.raises(WebSocketError) as exc:
            ws.run_forever()

        assert exc.value.code == WsCloseCode.INVALID_DATA
        assert close_called

    def test_run_forever_exhausts_retries(self) -> None:
        """Verifies that transient errors exceeding retry limits abort the loop."""
        mock_curl: Mock = Mock(spec=Curl)
        strategy: WebSocketRetryStrategy = WebSocketRetryStrategy(
            retry=True, count=2, delay=0.001
        )
        ws: WebSocket = WebSocket(curl=mock_curl, ws_retry=strategy)
        ws.closed = False
        ws._sock_fd = 999
        ws._read_selector = Mock()

        mock_curl.ws_recv.side_effect = CurlError("SSL Error", CurlECode.RECV_ERROR)

        error_called = False

        def on_error(w, exc) -> None:
            nonlocal error_called
            error_called = True
            assert isinstance(exc, CurlError)
            assert exc.code == CurlECode.RECV_ERROR

        ws._emitters["error"] = on_error

        with pytest.raises(CurlError):
            ws.run_forever()

        assert error_called


class TestWebSocketCloseAndState:
    def test_graceful_close(self, ws_connection: WebSocket) -> None:
        ws_connection.close(WsCloseCode.OK, b"goodbye")
        assert ws_connection.closed

    def test_close_idempotent(self, ws_connection: WebSocket) -> None:
        ws_connection.close()
        ws_connection.close()
        assert ws_connection.closed

    def test_recv_after_close_raises(self, ws_connection: WebSocket) -> None:
        ws_connection.close()
        with pytest.raises(WebSocketClosed):
            _ = ws_connection.recv(timeout=1.0)

    def test_send_after_close_raises(self, ws_connection: WebSocket) -> None:
        ws_connection.close()
        with pytest.raises((WebSocketClosed, WebSocketError)):
            _ = ws_connection.send(b"test", timeout=1.0)

    def test_close_code_extraction(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=1001,
            close_reason="going away",
        )

        ws: WebSocket = session.ws_connect(configurable_ws_server.url, autoclose=False)
        try:
            _ = ws.send(b"trigger", timeout=2.0)
            _ = ws.recv(timeout=5.0)  # Receive Echo
            _, flags = ws.recv(timeout=5.0)  # Receive Close
            assert flags & CurlWsFlag.CLOSE
            assert ws.close_code == 1001
            assert ws.close_reason == "going away"
        finally:
            ws.close()

    @pytest.mark.parametrize(
        "code,expected_valid",
        [
            (1000, True),
            (1001, True),
            (1002, True),
            (1003, True),
            (1007, True),
            (1008, True),
            (1009, True),
            (3000, True),
        ],
    )
    def test_valid_close_codes(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        code: int,
        expected_valid: bool,
    ) -> None:
        ws_config(behavior=ServerBehavior.ECHO)
        ws: WebSocket = session.ws_connect(configurable_ws_server.url)
        try:
            ws.close(code, b"test")
        except WebSocketError:
            if expected_valid:
                pytest.fail(f"Close code {code} should be valid")

    def test_close_with_long_reason(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.ECHO)
        ws: WebSocket = session.ws_connect(configurable_ws_server.url)
        long_reason: bytes = b"x" * 123
        ws.close(WsCloseCode.OK, long_reason)
        assert ws.closed

    def test_utf8_close_reason_roundtrip(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Ensures that non-ASCII close reasons (e.g., emojis/UTF-8 strings)
        are cleanly encoded, sent, and unpacked without raising unicode decode errors.
        """
        ws_config(behavior=ServerBehavior.ECHO)
        ws: WebSocket = session.ws_connect(configurable_ws_server.url, autoclose=False)

        unicode_reason = "Server maintenance 🚀"
        try:
            ws.close(WsCloseCode.GOING_AWAY, unicode_reason)
            assert ws.closed
            assert ws.close_code == WsCloseCode.GOING_AWAY
            assert ws.close_reason == unicode_reason
        finally:
            ws.close()

    def test_unpack_empty_close_frame(self) -> None:
        ws: WebSocket = WebSocket(curl=Mock())
        code, reason = ws._unpack_close_frame(b"")
        assert code == WsCloseCode.UNKNOWN
        assert reason == ""

    def test_unpack_code_only_close_frame(self) -> None:
        ws: WebSocket = WebSocket(curl=Mock())
        code, reason = ws._unpack_close_frame(b"\x03\xe8")
        assert code == WsCloseCode.OK
        assert reason == ""


class TestWebSocketIterator:
    def test_for_in_loop(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        messages: list[bytes] = [b"one", b"two", b"three"]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        with session.ws_connect(configurable_ws_server.url) as ws:
            received: list[bytes] = []

            for msg in ws:
                received.append(msg)
                if len(received) == len(messages):
                    break

            assert len(received) == 3
            assert received == messages

    def test_iterator_skips_control_frames(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        ws_config(behavior=ServerBehavior.SEND_PINGS)

        with session.ws_connect(configurable_ws_server.url) as ws:
            received: list[bytes] = []

            for msg in ws:
                received.append(msg)
                if len(received) == 2:
                    break

            assert received == [b"data_1", b"data_2"]


class TestWebSocketParameterBoundaries:
    def test_client_enforces_max_message_size(
        self,
        session: Session,
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        two_mb = 2 * 1024 * 1024
        ws_config(behavior=ServerBehavior.LARGE_RESPONSE, response_size=two_mb)

        with session.ws_connect(
            configurable_ws_server.url,
            max_message_size=1024 * 1024,  # Client limit is 1MB
        ) as ws:
            _ = ws.send(b"trigger", timeout=2.0)

            with pytest.raises(WebSocketError) as exc_info:
                _ = ws.recv(timeout=5.0)

            assert "Message too large" in str(exc_info.value)
            assert exc_info.value.code == CurlECode.TOO_LARGE


class TestWebSocketFragmentationFix:
    """Tests validating the manual memoryview slicing & boundary math."""

    def test_partial_write_exact_boundary_resumption(
        self, ws_connection: WebSocket
    ) -> None:
        original_ws_send: Callable[..., int] = ws_connection.curl.ws_send
        attempt_logs: list[tuple[int, int]] = []

        def mock_ws_send(chunk: memoryview, flags: int) -> int:
            chunk_len: int = len(chunk)
            if chunk_len == 65536 and len(attempt_logs) == 0:
                n_sent: int = 10000
            else:
                n_sent = chunk_len

            attempt_logs.append((chunk_len, n_sent))
            return original_ws_send(chunk[:n_sent], flags)

        with unittest.mock.patch.object(
            ws_connection.curl, "ws_send", side_effect=mock_ws_send
        ):
            payload: bytes = b"X" * 100000
            _ = ws_connection.send(payload, timeout=5.0)

            data, _ = ws_connection.recv(timeout=5.0)
            assert data == payload

            assert len(attempt_logs) == 3
            assert attempt_logs[0] == (65536, 10000)
            assert attempt_logs[1] == (55536, 55536)
            assert attempt_logs[2] == (34464, 34464)

    def test_send_eagain_retry_preserves_state(self, ws_connection: WebSocket) -> None:
        original_ws_send: Callable[..., int] = ws_connection.curl.ws_send
        call_count = 0

        def mock_ws_send(chunk: memoryview, flags: int) -> int:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise CurlError("Simulated EAGAIN", CurlECode.AGAIN)
            return original_ws_send(chunk, flags)

        with unittest.mock.patch.object(
            ws_connection.curl, "ws_send", side_effect=mock_ws_send
        ):
            payload: bytes = b"Y" * 100000
            _ = ws_connection.send(payload, timeout=5.0)
            data, _ = ws_connection.recv(timeout=5.0)

            assert data == payload
            assert call_count == 3


class TestWebSocketRobustness:
    def test_raw_fragment_assembly_with_interleaved_control_frames(self) -> None:
        """
        Proves that the inline recv() loop correctly reassembles fragmented data
        even when PING and PONG frames are maliciously interleaved by the server.
        """
        mock_curl: Mock = Mock(spec=Curl)
        ws: WebSocket = WebSocket(curl=mock_curl)
        ws.closed = False
        ws._sock_fd = 999

        # Mock the selectors to prevent registering the fake FD (999) with the OS
        mock_selector: Mock = Mock()
        ws._read_selector = mock_selector
        ws._write_selector = mock_selector

        class MockFrameMeta:
            def __init__(self, flags: int, bytesleft: int = 0) -> None:
                self.flags: int = flags
                self.bytesleft: int = bytesleft

        mock_sequence: list[tuple[bytes, MockFrameMeta]] = [
            (b"Chunk 1 ", MockFrameMeta(CurlWsFlag.TEXT | CurlWsFlag.CONT)),
            (b"ping_payload", MockFrameMeta(CurlWsFlag.PING)),
            (b"pong_payload", MockFrameMeta(CurlWsFlag.PONG)),
            (b"Chunk 2", MockFrameMeta(CurlWsFlag.TEXT)),
        ]

        iterator: Iterator[tuple[bytes, MockFrameMeta]] = iter(mock_sequence)
        mock_curl.ws_recv.side_effect = lambda: next(iterator)

        # Call the synchronous receive loop directly
        data, flags = ws.recv(timeout=5.0)

        # The loop MUST have bypassed the PING and PONG and cleanly glued the text.
        assert data == b"Chunk 1 Chunk 2"
        assert flags == CurlWsFlag.TEXT

    def test_abrupt_server_eof(self) -> None:
        """Verifies that an abrupt TCP drop resolves as an ABNORMAL_CLOSURE."""
        mock_curl: Mock = Mock(spec=Curl)
        ws: WebSocket = WebSocket(curl=mock_curl)
        ws.closed = False
        ws._sock_fd = 999
        ws._read_selector = Mock()
        mock_curl.ws_recv.side_effect = CurlError("EOF", CurlECode.GOT_NOTHING)

        with pytest.raises(WebSocketClosed) as exc:
            _ = ws.recv(timeout=1.0)
        assert exc.value.code == WsCloseCode.ABNORMAL_CLOSURE

    def test_send_write_stall_protection(self) -> None:
        """Prevents infinite spin-loops if the OS buffer refuses to accept bytes."""
        mock_curl: Mock = Mock(spec=Curl)
        ws: WebSocket = WebSocket(curl=mock_curl)
        ws.closed = False
        ws._sock_fd = 999
        ws._read_selector = Mock()
        ws._write_selector = Mock()
        mock_curl.ws_send.return_value = 0  # 0 bytes sent repeatedly

        with pytest.raises(WebSocketError) as exc:
            _ = ws.send(b"data", timeout=1.0)

        assert "Writer stalled" in str(exc.value)
        assert exc.value.code == CurlECode.WRITE_ERROR


class TestWebSocketSIMDEdgeCases:
    """Probes the C-layer SIMD / Scalar XOR boundary behavior via the API."""

    @pytest.mark.parametrize("extra_bytes", [0, 1, 2, 3, 4, 7, 31, 33, 63, 65])
    def test_simd_masking_tail_logic(
        self, ws_connection: WebSocket, extra_bytes: int
    ) -> None:
        size: int = 128 + extra_bytes
        payload: bytes = b"\xde\xad\xbe\xef" * (size // 4) + b"\xff" * (size % 4)
        payload = payload[:size]

        _ = ws_connection.send_binary(payload, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)

        assert len(data) == size
        assert data == payload

    def test_mask_index_persistence_across_unaligned_fragments(
        self, ws_connection: WebSocket
    ) -> None:
        chunks: list[bytes] = [b"ABC", b"DEF", b"GHI", b"JKL"]

        _ = ws_connection.send(chunks[0], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        _ = ws_connection.send(chunks[1], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        _ = ws_connection.send(chunks[2], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        _ = ws_connection.send(chunks[3], flags=CurlWsFlag.BINARY)

        data, _ = ws_connection.recv(timeout=5.0)
        assert data == b"ABCDEFGHIJKL"

    def test_unaligned_memory_source(self, ws_connection: WebSocket) -> None:
        base_data: bytes = b"AlignmentPadding" + b"ActualPayload" * 10
        unaligned_view: memoryview = memoryview(base_data)[7:]

        _ = ws_connection.send(unaligned_view, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == bytes(unaligned_view)

    def test_manual_fragmentation_with_empty_chunks(
        self, ws_connection: WebSocket
    ) -> None:
        _ = ws_connection.send(b"Start", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        _ = ws_connection.send(b"", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        _ = ws_connection.send(b"End", flags=CurlWsFlag.TEXT)

        response: str = ws_connection.recv_str(timeout=5.0)
        assert response == "StartEnd"

    @pytest.mark.parametrize("length", [1, 3, 15, 31, 63, 127])
    def test_simd_to_scalar_transition_boundaries(
        self, ws_connection: WebSocket, length: int
    ) -> None:
        payload: bytes = b"A" * length
        _ = ws_connection.send(payload, timeout=5.0)
        data, _ = ws_connection.recv(timeout=5.0)
        assert data == payload
        assert len(data) == length


class TestWebSocketThreadSafety:
    """Verifies that multiple independent synchronous clients run cleanly on threads."""

    def test_multithreaded_event_loops(
        self, configurable_ws_server: ConfigurableWSServer
    ) -> None:
        """
        Runs multiple threads simultaneously hitting the C-layer XOR masking
        functions. Ensures the global static CPU capability caching and memory
        doesn't crash or corrupt across threads.
        """

        def run_thread(thread_id: int) -> None:
            with (
                Session[Response]() as s,
                s.ws_connect(configurable_ws_server.url) as ws,
            ):
                for i in range(50):
                    payload: bytes = f"thread_{thread_id}_msg_{i}".encode()
                    _ = ws.send(payload, timeout=2.0)
                    data, _ = ws.recv(timeout=2.0)
                    assert data == payload

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures: list[Future[None]] = [
                executor.submit(run_thread, i) for i in range(5)
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()  # Will raise if assertion failed or exception occurred


class TestWebSocketRetryStrategy:
    def test_recv_retry_strategy_success(self) -> None:
        """
        Verifies that the WebSocketRetryStrategy successfully recovers from
        transient CurlECode.RECV_ERROR anomalies, retrying up to the limit
        and then returning the final successful frame.
        """
        mock_curl: Mock = Mock(spec=Curl)
        # Configure a retry strategy on the client
        strategy: WebSocketRetryStrategy = WebSocketRetryStrategy(
            retry=True, count=2, delay=0.01
        )
        ws: WebSocket = WebSocket(curl=mock_curl, ws_retry=strategy)
        ws.closed = False
        ws._sock_fd = 999

        # Mock selectors to avoid registering the fake FD
        mock_selector: Mock = Mock()
        ws._read_selector = mock_selector
        ws._write_selector = mock_selector

        class MockFrameMeta:
            def __init__(self) -> None:
                self.flags: int = CurlWsFlag.TEXT
                self.bytesleft: int = 0

        call_count = 0

        def mock_ws_recv() -> tuple[bytes, MockFrameMeta]:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Fail the first 2 times with a retryable code
                raise CurlError("Transient connection error", CurlECode.RECV_ERROR)
            return b"recovered_message", MockFrameMeta()

        mock_curl.ws_recv.side_effect = mock_ws_recv

        # Should recover on the third attempt and return the data
        data, flags = ws.recv(timeout=5.0)
        assert data == b"recovered_message"
        assert flags == CurlWsFlag.TEXT
        assert call_count == 3


class TestWebSocketPerformance:
    def test_high_volume_chatty_protocol(self, ws_connection: WebSocket) -> None:
        """
        Sends 2000 tiny frames to ensure the synchronous CFFI boundary remains
        lightning fast and doesn't leak memory.
        """
        for _ in range(2000):
            _ = ws_connection.send(b"K", timeout=1.0)
            data, _ = ws_connection.recv(timeout=1.0)
            assert data == b"K"
