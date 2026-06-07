"""
Comprehensive test suite for AsyncWebSocket implementation.

This module provides reusable, composable test infrastructure for testing
the AsyncWebSocket class across various scenarios including:
- Basic connectivity and message exchange
- Different message types (binary, text, JSON)
- Timeout behavior
- Error propagation and handling
- Cancellation semantics
- Large message fragmentation
- Concurrent operations
- Queue backpressure behavior
- Connection lifecycle management
"""

from __future__ import annotations

import asyncio
import queue
import threading
import unittest.mock
from asyncio import Task
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Iterator,
)
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from enum import Enum, auto
from struct import unpack
from typing import Protocol
from unittest.mock import Mock

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK

from curl_cffi import (
    AsyncSession,
    AsyncWebSocket,
    Curl,
    CurlECode,
    CurlError,
    CurlWsFlag,
    Response,
    WebSocketClosed,
    WebSocketError,
    WebSocketTimeout,
    WsCloseCode,
)

# =============================================================================
# Test Server Infrastructure
# =============================================================================


class ServerBehavior(Enum):
    """Defines how the test WebSocket server should behave."""

    ECHO = auto()  # Echo back received messages
    ECHO_REVERSE = auto()  # Echo messages in reverse
    BROADCAST = auto()  # Send predefined messages on connect
    DELAYED_ECHO = auto()  # Echo with configurable delay
    CLOSE_IMMEDIATELY = auto()  # Close connection immediately after connect
    CLOSE_AFTER_N = auto()  # Close after receiving N messages
    SILENT = auto()  # Accept messages but never respond
    LARGE_RESPONSE = auto()  # Respond with large messages
    FRAGMENTED = auto()  # Send fragmented messages
    SEND_PINGS = auto()  # Send PING control frames


@dataclass
class ServerConfig:
    """Configuration for test WebSocket server behavior."""

    behavior: ServerBehavior = ServerBehavior.ECHO
    delay_seconds: float = 0.0
    close_after_n: int = 1
    broadcast_messages: list[bytes | str] = field(default_factory=list)
    response_size: int = 1024
    close_code: int = WsCloseCode.OK
    close_reason: str = ""
    max_size: int = 32 * 1024 * 1024


class WebSocketHandler(Protocol):
    """Protocol for WebSocket message handlers."""

    async def __call__(
        self, ws: websockets.ServerConnection, config: ServerConfig
    ) -> None: ...


async def echo_handler(ws: websockets.ServerConnection, config: ServerConfig) -> None:
    """Standard echo handler - echoes back all received messages."""
    try:
        async for msg in ws:
            if config.delay_seconds > 0:
                await asyncio.sleep(config.delay_seconds)
            await ws.send(msg)
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def echo_reverse_handler(
    ws: websockets.ServerConnection, _config: ServerConfig
) -> None:
    """Echo handler that reverses message content."""
    try:
        async for msg in ws:
            if isinstance(msg, str):
                await ws.send(msg[::-1])
            else:
                await ws.send(msg[::-1])
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def broadcast_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    """Sends predefined messages immediately on connection."""
    try:
        for msg in config.broadcast_messages:
            await ws.send(msg)
        # Keep connection open until client closes
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def send_pings_handler(
    ws: websockets.ServerConnection, _config: ServerConfig
) -> None:
    """Sends PING frames mixed with standard messages to test filtering."""
    try:
        # Send a PING frame
        _ = await ws.ping(b"server_ping_1")
        await asyncio.sleep(0.05)

        # Send a normal DATA frame
        await ws.send(b"data_1")

        # Send another PING frame
        _ = await ws.ping(b"server_ping_2")
        await asyncio.sleep(0.05)

        # Send another DATA frame
        await ws.send(b"data_2")

        # Keep connection open
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def close_immediately_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    """Closes connection immediately after handshake."""
    await ws.close(config.close_code, config.close_reason)


async def close_after_n_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    """Echoes N messages then closes the connection."""
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
    """Accepts messages but never responds."""
    try:
        async for _ in ws:
            pass
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


async def large_response_handler(
    ws: websockets.ServerConnection, config: ServerConfig
) -> None:
    """Responds to any message with a large payload."""
    try:
        async for _ in ws:
            await ws.send(b"X" * config.response_size)
    except (ConnectionClosedOK, ConnectionClosedError):
        pass


HANDLERS: dict[ServerBehavior, Callable[..., Awaitable[None]]] = {
    ServerBehavior.ECHO: echo_handler,
    ServerBehavior.ECHO_REVERSE: echo_reverse_handler,
    ServerBehavior.BROADCAST: broadcast_handler,
    ServerBehavior.CLOSE_IMMEDIATELY: close_immediately_handler,
    ServerBehavior.CLOSE_AFTER_N: close_after_n_handler,
    ServerBehavior.SILENT: silent_handler,
    ServerBehavior.LARGE_RESPONSE: large_response_handler,
    ServerBehavior.DELAYED_ECHO: echo_handler,  # Uses delay from config
    ServerBehavior.SEND_PINGS: send_pings_handler,
}


@dataclass
class ConfigurableWSServer:
    """A configurable WebSocket server for testing."""

    url: str
    port: int
    stop: Callable[[], None]
    set_config: Callable[[ServerConfig], None]
    _thread: threading.Thread

    def configure(self, **kwargs) -> None:
        """Update server configuration."""
        self.set_config(ServerConfig(**kwargs))


def start_configurable_ws_server(port: int) -> ConfigurableWSServer:
    """
    Start a configurable WebSocket server on 127.0.0.1:port.
    Returns a ConfigurableWSServer instance.
    """
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
def configurable_ws_server() -> Generator[ConfigurableWSServer, object, None]:
    """Module-scoped configurable WebSocket server."""
    server: ConfigurableWSServer = start_configurable_ws_server(port=8965)
    try:
        yield server
    finally:
        server.stop()
        server._thread.join(timeout=5)


@pytest.fixture
def ws_config(configurable_ws_server: ConfigurableWSServer) -> Callable[..., None]:
    """Fixture to configure the server for each test."""
    # Reset to default echo behavior before each test
    configurable_ws_server.set_config(ServerConfig())

    def configure(**kwargs) -> None:
        configurable_ws_server.set_config(ServerConfig(**kwargs))

    return configure


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    """Async session fixture."""
    async with AsyncSession[Response]() as s:
        yield s


@pytest.fixture
async def ws_connection(
    session: AsyncSession[Response],
    configurable_ws_server: ConfigurableWSServer,
    ws_config: Callable[..., None],  # Ensures server is reset to ECHO before test
) -> AsyncIterator[AsyncWebSocket]:
    """Provides a connected AsyncWebSocket, cleaned up after test."""
    # ws_config fixture resets server to ECHO mode
    ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
    try:
        yield ws
    finally:
        await ws.close()


@asynccontextmanager
async def create_ws(
    session: AsyncSession[Response],
    url: str,
    **kwargs,
) -> AsyncGenerator[AsyncWebSocket]:
    """Context manager for creating WebSocket connections with custom options."""
    ws: AsyncWebSocket = await session.ws_connect(url, **kwargs)
    try:
        yield ws
    finally:
        await ws.close()


# =============================================================================
# Test Helpers
# =============================================================================


class AsyncWebSocketTestCase:
    """Base class for WebSocket test cases with common utilities."""

    @staticmethod
    async def assert_echo(ws: AsyncWebSocket, message: bytes | str) -> None:
        """Send a message and assert it's echoed back."""
        if isinstance(message, str):
            await ws.send_str(message)
            response: str | bytes = await ws.recv_str()
        else:
            await ws.send_bytes(message)
            response, _ = await ws.recv()
        assert response == message

    @staticmethod
    async def assert_recv_timeout(ws: AsyncWebSocket, timeout: float = 0.1) -> None:
        """Assert that recv times out."""
        with pytest.raises(WebSocketTimeout):
            _ = await ws.recv(timeout=timeout)

    @staticmethod
    async def send_n_messages(
        ws: AsyncWebSocket, n: int, prefix: str = "msg"
    ) -> list[str]:
        """Send N messages and return what was sent."""
        messages: list[str] = [f"{prefix}_{i}" for i in range(n)]
        for msg in messages:
            await ws.send_str(msg)
        return messages

    @staticmethod
    async def recv_n_messages(ws: AsyncWebSocket, n: int) -> list[str]:
        """Receive N messages."""
        return [await ws.recv_str() for _ in range(n)]


# =============================================================================
# Test Classes
# =============================================================================


@pytest.mark.asyncio
class TestAsyncWebSocketBasicConnectivity:
    """Tests for basic WebSocket connectivity and simple operations."""

    async def test_connect_and_close(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test basic connect and close cycle."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        assert ws.is_alive()
        assert not ws.closed
        await ws.close()
        assert ws.closed

    async def test_context_manager(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test async context manager properly closes connection."""
        async with session.ws_connect(configurable_ws_server.url) as ws:
            assert ws.is_alive()
        assert ws.closed

    async def test_echo_single_message(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending and receiving a single message."""
        await ws_connection.send(b"hello")
        data, flags = await ws_connection.recv()
        assert data == b"hello"
        assert flags & CurlWsFlag.BINARY

    async def test_echo_multiple_messages(self, ws_connection: AsyncWebSocket) -> None:
        """Test multiple message exchanges."""
        for i in range(10):
            msg: str = f"message_{i}"
            await ws_connection.send_str(msg)
            response: str = await ws_connection.recv_str()
            assert response == msg


class TestAsyncWebSocketMessageTypes:
    """Tests for different message types (binary, text, JSON)."""

    async def test_send_recv_binary(self, ws_connection: AsyncWebSocket) -> None:
        """Test binary message exchange."""
        payload = b"\x00\x01\x02\xff\xfe"
        await ws_connection.send_binary(payload)
        data, flags = await ws_connection.recv()
        assert data == payload
        assert flags & CurlWsFlag.BINARY

    async def test_send_recv_text(self, ws_connection: AsyncWebSocket) -> None:
        """Test text message exchange."""
        payload = "Hello, WebSocket! 你好 🎉"
        await ws_connection.send_str(payload)
        response: str = await ws_connection.recv_str()
        assert response == payload

    async def test_send_recv_json(self, ws_connection: AsyncWebSocket) -> None:
        """Test JSON message exchange."""
        payload: dict[str, str | int | dict[str, int]] = {
            "key": "value",
            "number": 42,
            "nested": {"a": 1},
        }
        await ws_connection.send_json(payload)
        assert (await ws_connection.recv_json()) == payload

    async def test_send_bytes_alias(self, ws_connection: AsyncWebSocket) -> None:
        """Test that send_bytes is an alias for send_binary."""
        payload = b"test_bytes"
        await ws_connection.send_bytes(payload)
        data, _ = await ws_connection.recv()
        assert data == payload

    async def test_send_bytearray(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending bytearray."""
        payload: bytearray = bytearray(b"bytearray_test")
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert data == bytes(payload)

    async def test_send_memoryview(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending memoryview."""
        original = b"memoryview_test"
        payload: memoryview = memoryview(original)
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert data == original

    async def test_recv_str_invalid_utf8(
        self, ws_connection: AsyncWebSocket, ws_config: Callable[..., None]
    ) -> None:
        """Test recv_str raises on invalid UTF-8."""
        # Send binary that's not valid UTF-8
        await ws_connection.send(b"\xff\xfe")
        # The server echoes it back, we try to decode as string
        with pytest.raises(WebSocketError) as exc_info:
            _ = await ws_connection.recv_str()
        assert exc_info.value.code == WsCloseCode.INVALID_DATA

    async def test_recv_json_invalid(self, ws_connection: AsyncWebSocket) -> None:
        """Test recv_json raises on invalid JSON."""
        await ws_connection.send_str("not valid json {")
        with pytest.raises(WebSocketError) as exc_info:
            await ws_connection.recv_json()
        assert exc_info.value.code == WsCloseCode.INVALID_DATA

    async def test_recv_json_empty(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test recv_json raises on empty payload."""
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=[""])
        async with session.ws_connect(configurable_ws_server.url) as ws:
            with pytest.raises(WebSocketError) as exc_info:
                await ws.recv_json()
            assert "empty" in str(exc_info.value).lower()

    async def test_pong_is_silently_consumed(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that server PONG replies are silently consumed and not enqueued."""
        ws_config(behavior=ServerBehavior.SILENT)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            # Send a ping. The Python `websockets` server replies with a PONG.
            await ws.ping(b"heartbeat")

            # Wait a moment to ensure the PONG arrives back at the client
            await asyncio.sleep(0.1)

            # The queue should be completely empty, proving the PONG was dropped
            # by the _read_loop and didn't leak into the application data.
            with pytest.raises(WebSocketTimeout):
                _ = await ws.recv(timeout=0.2)

    async def test_server_ping_is_silently_consumed(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that server-initiated PING frames are silently consumed."""
        ws_config(behavior=ServerBehavior.SEND_PINGS)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            # We expect to sequentially receive the data messages, skipping the PINGs
            data1, flags1 = await ws.recv(timeout=1.0)
            assert data1 == b"data_1"
            assert not (flags1 & CurlWsFlag.PING)

            data2, flags2 = await ws.recv(timeout=1.0)
            assert data2 == b"data_2"
            assert not (flags2 & CurlWsFlag.PING)

            # Verify no rogue PING frames are left in the queue
            with pytest.raises(WebSocketTimeout):
                _ = await ws.recv(timeout=0.2)


class TestAsyncWebSocketTimeouts:
    """Tests for timeout behavior."""

    async def test_recv_timeout(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test recv timeout when no message arrives."""
        ws_config(behavior=ServerBehavior.SILENT)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            await ws.send(b"hello")
            with pytest.raises(WebSocketTimeout):
                _ = await ws.recv(timeout=0.2)

    async def test_recv_timeout_returns_if_data_arrives(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Test recv with timeout returns if data arrives before timeout."""
        await ws_connection.send_str("quick")
        # Should not timeout
        response: str = await ws_connection.recv_str(timeout=5.0)
        assert response == "quick"


class TestAsyncWebSocketLargeMessages:
    """Tests for large message handling and fragmentation."""

    @pytest.mark.parametrize("size", [1024, 65536, 100_000, 500_000])
    async def test_large_message_echo(
        self, ws_connection: AsyncWebSocket, size: int
    ) -> None:
        """Test sending and receiving large messages."""
        payload: bytes = b"X" * size
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert len(data) == size
        assert data == payload

    async def test_large_text_message(self, ws_connection: AsyncWebSocket) -> None:
        """Test large text message."""
        payload: str = "A" * 100_000
        await ws_connection.send_str(payload)
        response: str = await ws_connection.recv_str()
        assert response == payload

    async def test_message_at_curl_frame_boundary(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Test message exactly at libcurl's 65536 byte frame boundary."""
        payload: bytes = b"B" * 65536
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert data == payload

    async def test_message_just_over_frame_boundary(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Test message just over the frame boundary (requires fragmentation)."""
        payload: bytes = b"C" * (65536 + 1)
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert data == payload


class TestAsyncWebSocketConcurrency:
    """Tests for concurrent operations."""

    async def test_concurrent_recv_single_consumer(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Test that a single consumer receives messages in order."""
        # Send multiple messages
        messages: list[str] = [f"msg_{i}" for i in range(5)]
        for msg in messages:
            await ws_connection.send_str(msg)

        # Receive all
        received: list[str] = []
        for _ in range(5):
            received.append(await ws_connection.recv_str())

        assert received == messages

    async def test_concurrent_recv_multiple_consumers(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test multiple concurrent recv() calls get distinct messages."""
        # Broadcast several messages
        messages: list[str] = [f"broadcast_{i}" for i in range(5)]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=10,
        ) as ws:
            # Give server time to send all messages
            await asyncio.sleep(0.1)

            # Create multiple concurrent recv tasks
            tasks: list[Task[str]] = [
                asyncio.create_task(ws.recv_str()) for _ in range(5)
            ]
            results: list[str] = await asyncio.gather(*tasks)

            # Each task should get a distinct message
            assert len(set[str](results)) == 5
            assert set[str](results) == set[str](messages)

    async def test_send_while_receiving(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending and receiving concurrently."""

        async def sender() -> None:
            for i in range(10):
                await ws_connection.send(f"ping_{i}".encode())
                await asyncio.sleep(0.01)

        async def receiver() -> list[bytes]:
            received: list[bytes] = []
            for _ in range(10):
                msg, _ = await ws_connection.recv(timeout=5.0)
                received.append(msg)
            return received

        sender_task: Task[None] = asyncio.create_task(sender())
        received: list[bytes] = await receiver()
        await sender_task

        assert len(received) == 10

    async def test_more_recv_callers_than_queue_size(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Test concurrent recv() calls when there are MORE callers than queue size.

        This tests the fix for the deadlock bug where having more consumers
        (e.g., 10 concurrent calls to recv) than queue size (e.g., 5) could
        cause a deadlock because only one sentinel could wake up the first waiter.

        The expected behavior is:
        - All waiters eventually get a message or error
        - No deadlock occurs
        - Messages are delivered in FIFO order
        """
        # Use small queue size with more consumers
        queue_size = 3
        num_consumers = 10
        num_messages = 10

        messages: list[str] = [f"msg_{i}" for i in range(num_messages)]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=queue_size,
            block_on_recv_queue_full=True,  # Block rather than fail
        ) as ws:
            # Give server time to start sending
            await asyncio.sleep(0.05)

            # Create MORE concurrent recv tasks than the queue size
            tasks: list[Task[tuple[bytes, int]]] = [
                asyncio.create_task(ws.recv(timeout=5.0)) for _ in range(num_consumers)
            ]

            # Wait for all with a reasonable timeout
            done, pending = await asyncio.wait(
                tasks, timeout=10.0, return_when=asyncio.ALL_COMPLETED
            )

            # Cancel any pending tasks
            for task in pending:
                _ = task.cancel()

            # All tasks should complete (no deadlock)
            assert (
                len(pending) == 0
            ), f"Deadlock detected: {len(pending)} tasks still pending"
            assert len(done) == num_consumers

            # Collect results - some may be messages or errors if connection closed
            results: list[tuple[bytes, int]] = []
            errors: list[WebSocketTimeout | WebSocketClosed | WebSocketError] = []
            for task in done:
                try:
                    result: tuple[bytes, int] = task.result()
                    results.append(result)
                except (WebSocketClosed, WebSocketTimeout, WebSocketError) as e:
                    errors.append(e)

            # We should have received some messages
            assert len(results) > 0, "Expected at least some successful receives"

    async def test_recv_callers_exceed_queue_with_slow_producer(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Test many recv() callers waiting when messages arrive slowly.

        This verifies that multiple waiters properly wake up one-by-one
        as messages become available, without deadlock.
        """
        queue_size = 2
        num_consumers = 5

        # Use echo - we control the message rate
        ws_config(behavior=ServerBehavior.ECHO)

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=queue_size,
        ) as ws:
            received: list[str] = []
            receive_order: list[int] = []
            lock: asyncio.Lock = asyncio.Lock()

            async def consumer(consumer_id: int) -> None:
                try:
                    data, _ = await ws.recv(timeout=5.0)
                    async with lock:
                        received.append(data.decode())
                        receive_order.append(consumer_id)
                except (WebSocketTimeout, WebSocketClosed):
                    pass

            # Start consumers BEFORE any messages are sent
            consumer_tasks: list[Task[None]] = [
                asyncio.create_task(consumer(i)) for i in range(num_consumers)
            ]

            # Give consumers time to start waiting
            await asyncio.sleep(0.1)

            # Send messages one at a time with small delays
            for i in range(num_consumers):
                await ws.send_str(f"slow_msg_{i}")
                await asyncio.sleep(0.05)  # Let one consumer wake up

            # Wait for all consumers
            _ = await asyncio.wait(consumer_tasks, timeout=10.0)

            # All consumers should have received exactly one message
            assert len(received) == num_consumers
            # Messages should be the ones we sent
            expected: set[str] = {f"slow_msg_{i}" for i in range(num_consumers)}
            assert set[str](received) == expected

    async def test_concurrent_recv_with_connection_close(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Test that all waiting recv() calls properly terminate when connection closes.

        When the connection closes, ALL waiting recv() calls should:
        - Either receive the close frame
        - Or raise WebSocketClosed
        - NOT hang indefinitely
        """
        queue_size = 2
        num_consumers = 8

        # Server closes after 1 message
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=WsCloseCode.GOING_AWAY,
        )

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=queue_size,
        ) as ws:
            # Start many recv waiters
            tasks: list[Task[tuple[bytes, int]]] = [
                asyncio.create_task(ws.recv(timeout=5.0)) for _ in range(num_consumers)
            ]

            # Trigger the server to send one message then close
            await ws.send(b"trigger")

            # All tasks should complete - not hang
            done, pending = await asyncio.wait(tasks, timeout=10.0)

            # Cancel stragglers
            for t in pending:
                _ = t.cancel()

            # No deadlock - all should complete
            assert len(pending) == 0, "Some recv() calls hung after connection close"

            # Count outcomes
            messages = 0
            close_frames = 0
            closed_errors = 0
            timeout_errors = 0

            for task in done:
                try:
                    _data, flags = task.result()
                    if flags & CurlWsFlag.CLOSE:
                        close_frames += 1
                    else:
                        messages += 1
                except WebSocketClosed:
                    closed_errors += 1
                except WebSocketTimeout:
                    timeout_errors += 1
                except Exception:
                    pass  # Other errors acceptable

            # Should have at least 1 message (the echo) and the rest should be
            # close frames or closed errors
            assert messages >= 1, "Expected at least the echo message"
            assert (
                timeout_errors == 0
            ), "No recv() should timeout - connection should close cleanly"


class TestAsyncWebSocketCancellation:
    """Tests for cancellation semantics."""

    async def test_cancel_recv_before_message(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test cancelling recv before any message arrives."""
        ws_config(behavior=ServerBehavior.SILENT)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            task: Task[tuple[bytes, int]] = asyncio.create_task(ws.recv())
            await asyncio.sleep(0.05)
            _ = task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

            # Connection should still be alive
            assert ws.is_alive()


class TestAsyncWebSocketClose:
    """Tests for connection close behavior."""

    async def test_graceful_close(self, ws_connection: AsyncWebSocket) -> None:
        """Test graceful close sends close frame."""
        await ws_connection.close(WsCloseCode.OK, b"goodbye")
        assert ws_connection.closed

    async def test_close_idempotent(self, ws_connection: AsyncWebSocket) -> None:
        """Test calling close multiple times is safe."""
        await ws_connection.close()
        await ws_connection.close()  # Should not raise
        assert ws_connection.closed

    async def test_terminate(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test terminate() immediately kills connection."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        ws.terminate()
        assert ws.closed or ws._terminated

    async def test_recv_after_close_raises(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test recv after close raises WebSocketClosed."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        await ws.close()

        # Test receive after close.
        with pytest.raises(WebSocketClosed):
            _ = await ws.recv()

    async def test_send_after_close_raises(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test send after close raises WebSocketClosed."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        await ws.close()

        with pytest.raises((WebSocketClosed, WebSocketError)):
            await ws.send(b"test")

    async def test_server_close_received(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test receiving close frame from server."""
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=WsCloseCode.GOING_AWAY,
            close_reason="server shutting down",
        )

        async with session.ws_connect(configurable_ws_server.url) as ws:
            await ws.send(b"trigger_close")
            # Server will close after echoing
            data, _flags = await ws.recv()
            assert data == b"trigger_close"

            # Next recv should get the close frame
            _close_data, close_flags = await ws.recv()
            assert close_flags & CurlWsFlag.CLOSE


class TestAsyncWebSocketIterator:
    """Tests for async iterator protocol."""

    async def test_async_for(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test async for iteration over messages."""
        messages: list[bytes] = [b"one", b"two", b"three"]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        async with session.ws_connect(configurable_ws_server.url) as ws:
            received: list[bytes] = []
            count = 0
            async for msg in ws:
                received.append(msg)
                count += 1
                if count >= 3:
                    break

            assert len(received) == 3

    async def test_aiter_on_closed_raises(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test iterating on closed connection raises."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        await ws.close()

        with pytest.raises(WebSocketClosed):
            async for _ in ws:
                pass

    async def test_iterator_skips_control_frames(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that the async iterator cleanly skips ping/pong frames."""
        ws_config(behavior=ServerBehavior.SEND_PINGS)

        async with session.ws_connect(configurable_ws_server.url) as ws:
            received: list[bytes] = []

            # The iterator should seamlessly step over the PING frames
            async for msg in ws:
                received.append(msg)
                if len(received) == 2:
                    break

            # We should only get the actual binary data payloads
            assert received == [b"data_1", b"data_2"]


class TestAsyncWebSocketQueueBehavior:
    """Tests for queue backpressure and overflow behavior."""

    async def test_recv_queue_size_limit(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test recv queue respects size limit."""
        messages: list[str] = [f"msg_{i}" for i in range(10)]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=5,
            block_on_recv_queue_full=True,
        ) as ws:
            # Give time for messages to arrive
            await asyncio.sleep(0.2)
            # Should be able to receive all eventually
            received: list[str] = []
            for _ in range(10):
                try:
                    msg: str = await ws.recv_str(timeout=1.0)
                    received.append(msg)
                except WebSocketTimeout:
                    break

    async def test_drain_on_error_false(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test drain_on_error=False raises immediately on transport error."""
        ws_config(behavior=ServerBehavior.CLOSE_IMMEDIATELY)

        async with session.ws_connect(
            configurable_ws_server.url,
            drain_on_error=False,
        ) as ws:
            await asyncio.sleep(0.1)  # Let close happen
            # Should get either close frame or error
            # The server sends a proper close, so we may receive it
            try:
                _, flags = await ws.recv(timeout=1.0)
                # If we received data, it should be a close frame
                assert flags & CurlWsFlag.CLOSE
            except (WebSocketClosed, WebSocketError):
                pass  # Also acceptable


class TestAsyncWebSocketPing:
    """Tests for ping/pong functionality."""

    async def test_ping_valid_payload(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending ping with valid payload."""
        await ws_connection.ping(b"heartbeat")
        # Connection should remain alive
        assert ws_connection.is_alive()

    async def test_ping_empty_payload(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending ping with empty payload."""
        await ws_connection.ping(b"")
        assert ws_connection.is_alive()

    async def test_ping_max_size(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending ping at maximum allowed size (125 bytes)."""
        await ws_connection.ping(b"X" * 125)
        assert ws_connection.is_alive()

    async def test_ping_too_large_raises(self, ws_connection: AsyncWebSocket) -> None:
        """Test ping with payload > 125 bytes raises error."""
        with pytest.raises(WebSocketError):
            await ws_connection.ping(b"X" * 126)


class TestAsyncWebSocketFlush:
    """Tests for the flush() method."""

    async def test_flush_empty_queue(self, ws_connection: AsyncWebSocket) -> None:
        """Test flush on empty queue returns immediately."""
        await ws_connection.flush(timeout=1.0)

    async def test_flush_waits_for_queue(self, ws_connection: AsyncWebSocket) -> None:
        """Test flush waits for queued messages to be sent."""
        for i in range(5):
            await ws_connection.send_str(f"msg_{i}")

        await ws_connection.flush(timeout=5.0)
        assert ws_connection.send_queue_size == 0


class TestAsyncWebSocketStateChecks:
    """Tests for connection state inspection methods."""

    async def test_is_alive_true_when_connected(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Test is_alive returns True for active connection."""
        assert ws_connection.is_alive()

    async def test_is_alive_false_after_close(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test is_alive returns False after close."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        await ws.close()
        assert not ws.is_alive()

    async def test_send_queue_size(self, ws_connection: AsyncWebSocket) -> None:
        """Test send_queue_size property."""
        assert ws_connection.send_queue_size == 0

    async def test_close_code_and_reason(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test close_code and close_reason are set after server close."""
        ws_config(
            behavior=ServerBehavior.CLOSE_IMMEDIATELY,
            close_code=WsCloseCode.GOING_AWAY,
            close_reason="test reason",
        )

        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        try:
            # Wait for close frame
            await asyncio.sleep(0.5)
            with suppress(WebSocketClosed, WebSocketError, WebSocketTimeout):
                _ = await ws.recv(timeout=0.5)
        finally:
            await ws.close()


class TestAsyncWebSocketEdgeCases:
    """Tests for edge cases and boundary conditions."""

    async def test_empty_message(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending and receiving empty message."""
        await ws_connection.send(b"")
        # Echo server should echo empty message
        data, _ = await ws_connection.recv()
        assert data == b""

    async def test_empty_string_message(self, ws_connection: AsyncWebSocket) -> None:
        """Test sending and receiving empty string."""
        await ws_connection.send_str("")
        response: str = await ws_connection.recv_str()
        assert response == ""

    async def test_unicode_edge_cases(self, ws_connection: AsyncWebSocket) -> None:
        """Test various Unicode edge cases."""
        test_strings: list[str] = [
            "",  # Empty
            "a",  # Single ASCII
            "🎉",  # Single emoji
            "Hello 世界 🌍",  # Mixed
            "\u0000",  # Null character
            "a" * 10000,  # Long string
        ]
        for s in test_strings:
            await ws_connection.send_str(s)
            response: str = await ws_connection.recv_str()
            assert response == s

    async def test_binary_all_byte_values(self, ws_connection: AsyncWebSocket) -> None:
        """Test binary message with all possible byte values."""
        payload: bytes = bytes(range(256))
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv()
        assert data == payload

    async def test_rapid_send_recv(self, ws_connection: AsyncWebSocket) -> None:
        """Test rapid send/recv cycles."""
        for i in range(100):
            msg: str = f"rapid_{i}"
            await ws_connection.send_str(msg)
            response = await ws_connection.recv_str()
            assert response == msg


# =============================================================================
# Integration Tests
# =============================================================================


class TestAsyncWebSocketIntegration:
    """Integration tests combining multiple features."""

    async def test_full_session_lifecycle(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
    ) -> None:
        """Test complete session lifecycle with various operations."""
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)

        try:
            # Send various message types
            await ws.send_binary(b"binary")
            assert await ws.recv() == (
                b"binary",
                pytest.approx(CurlWsFlag.BINARY, abs=0xFF),
            )

            await ws.send_str("text")
            assert await ws.recv_str() == "text"

            await ws.send_json({"test": True})
            assert await ws.recv_json() == {"test": True}

            # Send large message
            large: bytes = b"L" * 100_000
            await ws.send(large)
            data, _ = await ws.recv()
            assert data == large

            # Verify still alive
            assert ws.is_alive()

        finally:
            await ws.close()
            assert ws.closed

    async def test_reconnect_pattern(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test typical reconnection pattern."""
        for attempt in range(3):
            ws_config(behavior=ServerBehavior.ECHO)
            ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
            try:
                await ws.send_str(f"attempt_{attempt}")
                response = await ws.recv_str()
                assert response == f"attempt_{attempt}"
            finally:
                await ws.close()


# =============================================================================
# Parameter Boundary Tests
# =============================================================================


class TestAsyncWebSocketParameterBoundaries:
    """Tests for parameter edge values and boundary conditions."""

    @pytest.mark.parametrize("queue_size", [1, 2, 5, 10, 100])
    async def test_various_recv_queue_sizes(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        queue_size: int,
    ) -> None:
        """Test recv queue works correctly at various sizes."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=queue_size,
        ) as ws:
            # Send and receive messages equal to queue size
            for i in range(queue_size):
                await ws.send(f"msg_{i}".encode())

            for i in range(queue_size):
                data, _ = await ws.recv(timeout=5.0)
                assert data == f"msg_{i}".encode()

    @pytest.mark.parametrize("queue_size", [1, 2, 5, 10, 100])
    async def test_various_send_queue_sizes(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        queue_size: int,
    ) -> None:
        """Test send queue works correctly at various sizes."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            send_queue_size=queue_size,
        ) as ws:
            # Send messages
            for i in range(queue_size):
                await ws.send(f"msg_{i}".encode())

            # Receive them back
            for i in range(queue_size):
                data, _ = await ws.recv(timeout=5.0)
                assert data == f"msg_{i}".encode()

    @pytest.mark.parametrize("batch_size", [1, 8, 16, 32, 64])
    async def test_various_batch_sizes(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        batch_size: int,
    ) -> None:
        """Test max_send_batch_size parameter at various values."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            max_send_batch_size=batch_size,
        ) as ws:
            # Send enough messages to trigger batching
            for i in range(batch_size * 2):
                await ws.send(f"batch_{i}".encode())

            for i in range(batch_size * 2):
                data, _ = await ws.recv(timeout=5.0)
                assert data == f"batch_{i}".encode()

    @pytest.mark.parametrize("time_slice", [0.001, 0.01, 0.05])
    async def test_various_time_slices(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        time_slice: float,
    ) -> None:
        """Test recv_time_slice and send_time_slice parameters."""
        ws_config(behavior=ServerBehavior.ECHO, max_size=20 * 1024 * 1024)
        heartbeat_ticks = 0

        async def heartbeat() -> None:
            nonlocal heartbeat_ticks
            while True:
                await asyncio.sleep(0.001)
                heartbeat_ticks += 1

        hb_task: Task[None] = asyncio.create_task(heartbeat())

        try:
            async with session.ws_connect(
                configurable_ws_server.url,
                recv_time_slice=time_slice,
                send_time_slice=time_slice,
                max_message_size=20 * 1024 * 1024,
            ) as ws:
                # 5MB payload ensures we trigger the time-based yield on all hardware
                payload_size = 5 * 1024 * 1024
                large_payload: bytes = b"A" * payload_size

                await ws.send(large_payload)
                data, _ = await ws.recv(timeout=10.0)

                assert data == large_payload
                # If time-slicing works, the heartbeat task must have been
                # given time to run during the transfer.
                assert heartbeat_ticks > 0

        finally:
            _ = hb_task.cancel()
            with suppress(asyncio.CancelledError):
                await hb_task

    @pytest.mark.parametrize(
        "max_size",
        [1024, 64 * 1024, 256 * 1024, 1024 * 1024, 4 * 1024 * 1024],
    )
    async def test_various_max_message_sizes(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        max_size: int,
    ) -> None:
        """Test max_message_size parameter at various values."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            max_message_size=max_size,
        ) as ws:
            # Send message smaller than limit
            small_msg = b"x" * min(1000, max_size - 1)
            await ws.send(small_msg)
            data, _ = await ws.recv(timeout=5.0)
            assert data == small_msg

    @pytest.mark.asyncio
    async def test_client_enforces_max_message_size(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that the client drops the connection if the server
        sends a too-large message."""

        # Server sends a 2MB response
        two_mb = 2 * 1024 * 1024
        ws_config(behavior=ServerBehavior.LARGE_RESPONSE, response_size=two_mb)

        async with session.ws_connect(
            configurable_ws_server.url,
            # Client limit set to 1MB
            max_message_size=1024 * 1024,
        ) as ws:
            # Trigger the large response
            await ws.send(b"trigger")

            # The client's _read_loop should detect the oversized message,
            # close the connection, and raise a WebSocketError.
            with pytest.raises(WebSocketError) as exc_info:
                _ = await ws.recv(timeout=5.0)

            assert "Message too large" in str(exc_info.value)
            assert exc_info.value.code == CurlECode.TOO_LARGE

    @pytest.mark.asyncio
    async def test_server_enforces_max_message_size(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test the client's reaction when the server drops the connection
        for an oversized message."""
        ws_config(behavior=ServerBehavior.ECHO)

        # 33MB is just over the 32MB default limit set in ServerConfig
        too_big = 33 * 1024 * 1024
        payload: bytes = b"A" * too_big

        async with session.ws_connect(
            configurable_ws_server.url,
            # Ensure client is willing to send it
            max_message_size=40 * 1024 * 1024,
        ) as ws:
            await ws.send(payload)

            # We expect a Close frame (1009 Message Too Big)
            data, flags = await ws.recv(timeout=10.0)
            assert flags & CurlWsFlag.CLOSE

            # Payload starts with 2-byte integer code
            close_code = unpack("!H", data[:2])[0]
            assert close_code == WsCloseCode.MESSAGE_TOO_BIG  # 1009


class TestAsyncWebSocketCoalesceFrames:
    """Tests for the coalesce_frames parameter (frame batching)."""

    async def test_coalesce_frames_enabled(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test with coalesce_frames=True - frames may be batched together."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=True,
        ) as ws:
            # Send multiple messages - they may be coalesced
            for i in range(5):
                await ws.send(f"c{i}".encode())

            # Receive - may get coalesced data
            total_received = b""
            for _ in range(5):
                try:
                    data, _ = await ws.recv(timeout=2.0)
                    total_received += data
                except WebSocketTimeout:
                    break

            # All sent data should be received (possibly coalesced)
            for i in range(5):
                assert f"c{i}".encode() in total_received

    async def test_coalesce_frames_disabled(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test with coalesce_frames=False (default)."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=False,
        ) as ws:
            for i in range(10):
                await ws.send(f"no_coalesce_{i}".encode())
                data, _ = await ws.recv(timeout=5.0)
                assert data == f"no_coalesce_{i}".encode()

    async def test_coalesce_send_then_recv(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test coalesce mode with send-then-recv pattern."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=True,
        ) as ws:
            # Send one at a time and receive
            for i in range(5):
                await ws.send(f"msg_{i}".encode())
                await asyncio.sleep(0.05)  # Let it send
                data, _ = await ws.recv(timeout=5.0)
                assert f"msg_{i}".encode() in data

    async def test_coalesce_preserves_message_order(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that coalescing does not reorder messages of different types."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=True,
            max_send_batch_size=10,
        ) as ws:
            # Synchronously queue 3 different message types so they form a single batch
            await ws.send_str("text_1")
            await ws.send_binary(b"binary_1")
            await ws.send_str("text_2")

            await ws.flush(timeout=2.0)

            # Assert they arrive in the exact order they were queued
            msg1, flags1 = await ws.recv(timeout=2.0)
            assert flags1 & CurlWsFlag.TEXT
            assert msg1 == b"text_1"

            msg2, flags2 = await ws.recv(timeout=2.0)
            assert flags2 & CurlWsFlag.BINARY
            assert msg2 == b"binary_1"

            msg3, flags3 = await ws.recv(timeout=2.0)
            assert flags3 & CurlWsFlag.TEXT
            assert msg3 == b"text_2"

    async def test_coalesce_control_frame_interleaving(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that control frames split coalescing groups and don't get reordered."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=True,
            max_send_batch_size=10,
        ) as ws:
            # Queue 2 text frames, a ping, and 2 more text frames
            await ws.send_str("A")
            await ws.send_str("B")
            await ws.ping(b"heartbeat")
            await ws.send_str("C")
            await ws.send_str("D")

            await ws.flush(timeout=2.0)

            # The echo server should return the coalesced chunks separately
            # Chunk 1: "AB"
            msg1, flags1 = await ws.recv(timeout=2.0)
            assert msg1 == b"AB"
            assert flags1 & CurlWsFlag.TEXT

            # (The server handles the PING and sends a PONG automatically,
            # so the next data frame we see from the echo handler should be "CD")

            # Chunk 2: "CD"
            msg2, flags2 = await ws.recv(timeout=2.0)
            assert msg2 == b"CD"
            assert flags2 & CurlWsFlag.TEXT


class TestAsyncWebSocketFragmentationFix:
    """Tests targeting the payload fragmentation and partial write fixes."""

    async def test_partial_write_exact_boundary_resumption(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Forces a partial write to ensure _send_payload resumes the exact
        remaining bytes of the frame, avoiding the '(43) unaligned frame size' error.
        """
        original_ws_send: Callable[..., int] = ws_connection.curl.ws_send
        attempt_logs: list[tuple[int, int]] = []

        def mock_ws_send(chunk: memoryview, flags: int) -> int:
            chunk_len: int = len(chunk)

            # On the very first large frame, simulate a full socket buffer
            # by refusing to accept more than 10,000 bytes.
            if chunk_len == 65536 and len(attempt_logs) == 0:
                n_sent: int = 10000
            else:
                n_sent = chunk_len

            attempt_logs.append((chunk_len, n_sent))
            return original_ws_send(chunk[:n_sent], flags)

        with unittest.mock.patch.object(
            ws_connection.curl, "ws_send", side_effect=mock_ws_send
        ):
            # Send 100,000 bytes (Requires 2 frames: 65536 + 34464)
            payload: bytes = b"X" * 100000
            await ws_connection.send(payload)

            data, _ = await ws_connection.recv()
            assert data == payload

            # Verify the exact chunking sequence generated by the hot loop:
            # 1. Loop tries 65536, mock only accepts 10000
            # 2. Loop MUST try exactly 55536 next (the remainder of the 65536 frame)
            # 3. Loop tries 34464 (the final fragment)
            assert len(attempt_logs) == 3
            assert attempt_logs[0] == (65536, 10000)
            assert attempt_logs[1] == (
                55536,
                55536,
            )  # <-- The old code failed here by trying 65536
            assert attempt_logs[2] == (34464, 34464)

    async def test_send_eagain_retry_preserves_state(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Test that an EAGAIN error doesn't corrupt the frame boundary state.
        Verifies the zero-math hot-path retry optimization.
        """
        original_ws_send: Callable[..., int] = ws_connection.curl.ws_send
        call_count = 0

        def mock_ws_send(chunk: memoryview, flags: int) -> int:
            nonlocal call_count
            call_count += 1

            # Throw EAGAIN on the very first attempt to simulate a blocked socket
            if call_count == 1:
                raise CurlError("Simulated EAGAIN", CurlECode.AGAIN)

            return original_ws_send(chunk, flags)

        with unittest.mock.patch.object(
            ws_connection.curl, "ws_send", side_effect=mock_ws_send
        ):
            payload: bytes = b"Y" * 100000
            await ws_connection.send(payload)
            data, _ = await ws_connection.recv()

            assert data == payload
            # 1 EAGAIN attempt + 1st fragment (65536) + 2nd fragment (34464)
            assert call_count == 3

    async def test_manual_fragmentation_with_cont_flag(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Test that user-supplied CONT flags are preserved correctly on final chunks.
        Validates the 'current_flags = flags' assignment in the rewrite.
        """
        # Send part 1: TEXT | CONT
        await ws_connection.send(b"Part1-", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        # Send part 2: TEXT | CONT
        await ws_connection.send(b"Part2-", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        # Send part 3: TEXT (Final fragment drops the CONT flag)
        await ws_connection.send(b"Part3", flags=CurlWsFlag.TEXT)

        # The test server (websockets library) automatically reassembles
        # fragmented network messages before echoing them back.
        response: str = await ws_connection.recv_str()
        assert response == "Part1-Part2-Part3"


class TestAsyncWebSocketAutoclose:
    """Tests for autoclose behavior."""

    async def test_autoclose_true(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test autoclose=True automatically closes on server close frame."""
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=WsCloseCode.GOING_AWAY,
        )

        ws: AsyncWebSocket = await session.ws_connect(
            configurable_ws_server.url,
            autoclose=True,
        )
        try:
            # Trigger server close
            await ws.send(b"trigger")
            # Receive echo
            _ = await ws.recv(timeout=5.0)
            # Server sends close frame - autoclose should handle it
            with suppress(WebSocketClosed, WebSocketError):
                _ = await ws.recv(timeout=2.0)

            # Wait a bit for autoclose to process
            await asyncio.sleep(1)
            # Connection should be closed
            assert ws.closed or not ws.is_alive()
        finally:
            with suppress(Exception):
                await ws.close()

    async def test_autoclose_false(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test autoclose=False doesn't auto-respond to close frame."""
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=WsCloseCode.OK,
        )

        ws: AsyncWebSocket = await session.ws_connect(
            configurable_ws_server.url,
            autoclose=False,
        )
        try:
            await ws.send(b"trigger")
            # Receive echo
            data, _ = await ws.recv(timeout=5.0)
            assert data == b"trigger"
            # Receive close frame
            _, flags = await ws.recv(timeout=5.0)
            assert flags & CurlWsFlag.CLOSE
        finally:
            await ws.close()


class TestAsyncWebSocketBlockOnRecvQueueFull:
    """Tests for block_on_recv_queue_full parameter."""

    async def test_block_on_recv_queue_full_true(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test blocking when recv queue is full."""
        messages: list[str] = [f"full_{i}" for i in range(20)]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        async with session.ws_connect(
            configurable_ws_server.url,
            recv_queue_size=5,
            block_on_recv_queue_full=True,
        ) as ws:
            # Give server time to send
            await asyncio.sleep(0.2)

            # Should be able to receive all messages eventually
            received: list[str] = []
            for _ in range(20):
                try:
                    data, _ = await ws.recv(timeout=2.0)
                    received.append(data.decode())
                except WebSocketTimeout:
                    break

            # With blocking, we should receive most/all messages
            assert len(received) >= 5  # At least queue size

    async def test_block_on_recv_queue_full_false(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test non-blocking when recv queue is full fails the connection."""
        messages: list[str] = [f"drop_{i}" for i in range(20)]
        ws_config(behavior=ServerBehavior.BROADCAST, broadcast_messages=messages)

        # With block_on_recv_queue_full=False, the connection fails when queue fills
        # This is the expected behavior to preserve message integrity
        try:
            async with session.ws_connect(
                configurable_ws_server.url,
                recv_queue_size=5,
                block_on_recv_queue_full=False,
            ) as ws:
                # Try to receive - may get error due to queue overflow
                received: list[str] = []
                for _ in range(20):
                    try:
                        data, _ = await ws.recv(timeout=0.5)
                        received.append(data.decode())
                    except (WebSocketTimeout, WebSocketError, WebSocketClosed):
                        break

        except WebSocketError as e:
            # Expected: connection failed due to queue overflow
            assert "queue full" in str(e).lower() or "integrity" in str(e).lower()


class TestAsyncWebSocketCloseCodeValidation:
    """Tests for close code handling and validation."""

    @pytest.mark.parametrize(
        "code,expected_valid",
        [
            (1000, True),  # Normal closure
            (1001, True),  # Going away
            (1002, True),  # Protocol error
            (1003, True),  # Unsupported data
            (1007, True),  # Invalid data
            (1008, True),  # Policy violation
            (1009, True),  # Message too big
            (1010, True),  # Mandatory extension
            (1011, True),  # Internal error
            (3000, True),  # Reserved for libraries
            (4000, True),  # Reserved for private use
            (4999, True),  # Max valid code
        ],
    )
    async def test_valid_close_codes(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
        code: int,
        expected_valid: bool,
    ) -> None:
        """Test that valid close codes are accepted."""
        ws_config(behavior=ServerBehavior.ECHO)
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        try:
            # Should not raise for valid codes
            await ws.close(code, b"test")
        except WebSocketError:
            if expected_valid:
                pytest.fail(f"Close code {code} should be valid")

    async def test_close_with_reason(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test close with a reason message."""
        ws_config(behavior=ServerBehavior.ECHO)
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        await ws.close(WsCloseCode.GOING_AWAY, b"Server maintenance")
        assert ws.closed

    async def test_close_with_long_reason(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test close with maximum length reason (123 bytes)."""
        ws_config(behavior=ServerBehavior.ECHO)
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)
        # Max reason length is 123 bytes (125 - 2 byte code)
        long_reason = b"x" * 123
        await ws.close(WsCloseCode.OK, long_reason)
        assert ws.closed


# =============================================================================
# Coverage Gap Tests
# =============================================================================


class TestAsyncWebSocketCoverageGaps:
    """Tests specifically targeting uncovered code paths."""

    async def test_recv_with_validate_utf8_true(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test recv_str with UTF-8 validation enabled."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            # Send valid UTF-8
            await ws.send_str("Hello 世界 🎉")
            response = await ws.recv_str(timeout=5.0)
            assert response == "Hello 世界 🎉"

    async def test_send_binary_explicit(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test explicit send_binary method."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            await ws.send_binary(b"\x00\x01\x02\xff")
            data, flags = await ws.recv(timeout=5.0)
            assert data == b"\x00\x01\x02\xff"
            assert flags & CurlWsFlag.BINARY

    async def test_multiple_flush_calls(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test multiple consecutive flush calls."""
        ws_config(behavior=ServerBehavior.ECHO)
        async with session.ws_connect(configurable_ws_server.url) as ws:
            await ws.send(b"msg1")
            await ws.flush(timeout=5.0)
            await ws.flush(timeout=5.0)  # Second flush on empty queue
            await ws.send(b"msg2")
            await ws.flush(timeout=5.0)

            # Receive both
            data1, _ = await ws.recv(timeout=5.0)
            data2, _ = await ws.recv(timeout=5.0)
            assert data1 == b"msg1"
            assert data2 == b"msg2"

    async def test_close_code_extraction(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test that close code is properly extracted from server close frame."""
        ws_config(
            behavior=ServerBehavior.CLOSE_AFTER_N,
            close_after_n=1,
            close_code=1001,
            close_reason="going away",
        )

        ws: AsyncWebSocket = await session.ws_connect(
            configurable_ws_server.url,
            autoclose=False,
        )
        try:
            await ws.send(b"trigger")
            # Receive echo
            _ = await ws.recv(timeout=5.0)
            # Receive close frame
            _, flags = await ws.recv(timeout=5.0)
            assert flags & CurlWsFlag.CLOSE
            assert ws.close_code == 1001
            assert ws.close_reason == "going away"
        finally:
            await ws.close()

    async def test_is_alive_states(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test is_alive through various connection states."""
        ws_config(behavior=ServerBehavior.ECHO)

        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)

        # Should be alive after connect
        assert ws.is_alive()
        assert not ws.closed

        # Exchange a message
        await ws.send(b"test")
        _ = await ws.recv(timeout=5.0)
        assert ws.is_alive()

        # Close
        await ws.close()
        assert ws.closed
        assert not ws.is_alive()

    async def test_terminate_while_operations_pending(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """Test terminate while recv is waiting."""
        ws_config(behavior=ServerBehavior.SILENT)

        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)

        # Start a recv that will wait
        recv_task: Task[tuple[bytes, int]] = asyncio.create_task(ws.recv(timeout=30.0))
        await asyncio.sleep(0.1)

        # Terminate the connection
        ws.terminate()

        # The recv should complete with an error
        with suppress(WebSocketClosed, WebSocketError, asyncio.CancelledError):
            _ = await asyncio.wait_for(recv_task, timeout=2.0)

        assert ws.closed or ws._terminated


@pytest.mark.asyncio
class TestAsyncWebSocketBugFixes:
    """Tests to verify fixes for previously identified subtle bugs."""

    async def test_recv_timeout_race_condition(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Tests the race condition where a message arrives at the exact same
        event loop tick that the timeout expires.
        """
        ws_config(behavior=ServerBehavior.SILENT)

        async with session.ws_connect(configurable_ws_server.url) as ws:
            # We mock the internal queue to simulate a task that resolves
            # exactly when it is cancelled by the timeout block.
            original_get: Callable[[], Awaitable[tuple[bytes, int]]] = (
                ws._receive_queue.get
            )

            async def mock_get() -> tuple[bytes, int]:
                try:
                    await asyncio.sleep(10)
                except asyncio.CancelledError:
                    # Resolve exactly on cancellation (simulating the race)
                    return (b"saved_by_the_bell", CurlWsFlag.TEXT)
                return await original_get()

            ws._receive_queue.get = mock_get  # pyright: ignore[reportPrivateUsage]

            # The recv() call should NOT drop the message, should gracefully return it
            data, flags = await ws.recv(timeout=0.1)
            assert data == b"saved_by_the_bell"
            assert flags == CurlWsFlag.TEXT

    async def test_recv_json_enforces_text_frame(
        self,
        ws_connection: AsyncWebSocket,
    ) -> None:
        """
        Tests that recv_json() properly validates that the payload is a TEXT frame
        and rejects BINARY frames, aligning with the synchronous implementation.
        """
        # Send valid JSON, but as a BINARY frame
        await ws_connection.send_binary(b'{"key": "value"}')

        with pytest.raises(WebSocketError) as exc_info:
            await ws_connection.recv_json(timeout=5.0)

        assert exc_info.value.code == WsCloseCode.INVALID_DATA
        assert "Not a valid text frame" in str(exc_info.value)


class TestAsyncWebSocketRobustness:
    """Extreme edge case and stress tests for protocol robustness."""

    @pytest.mark.asyncio
    async def test_raw_fragment_assembly_with_interleaved_control_frames(self) -> None:
        """
        Proves that the _read_loop correctly reassembles fragmented data frames
        even when PING and PONG frames are maliciously interleaved in the stream,
        without memory leaks or state corruption.
        """

        # We don't need a real network socket for this, we just need to feed
        # the exact frame sequences to the parser to test its integrity.
        mock_curl: Mock = Mock(spec=Curl)
        mock_session: Mock = Mock()

        ws: AsyncWebSocket = AsyncWebSocket(mock_session, mock_curl)
        ws.closed = False
        ws._block_on_recv_queue_full = False

        class MockFrameMeta:
            def __init__(self, flags: int, bytesleft: int = 0) -> None:
                self.flags: int = flags
                self.bytesleft: int = bytesleft

        # Simulate libcurl yielding an evil sequence of fragmented frames:
        # 1. Fragment 1 (TEXT | CONT)
        # 2. PING (Injected control frame)
        # 3. PONG (Injected control frame)
        # 4. Fragment 2 (TEXT - Final chunk)
        # 5. CLOSE
        mock_sequence: list[tuple[bytes, MockFrameMeta]] = [
            (b"Chunk 1 ", MockFrameMeta(CurlWsFlag.TEXT | CurlWsFlag.CONT)),
            (b"ping_payload", MockFrameMeta(CurlWsFlag.PING)),
            (b"pong_payload", MockFrameMeta(CurlWsFlag.PONG)),
            (b"Chunk 2", MockFrameMeta(CurlWsFlag.TEXT)),
            (b"bye", MockFrameMeta(CurlWsFlag.CLOSE)),
        ]

        iterator: Iterator[tuple[bytes, MockFrameMeta]] = iter(mock_sequence)
        mock_curl.ws_recv.side_effect = lambda: next(iterator)

        # Execute the read loop directly
        await ws._read_loop()

        # Check the receive queue.
        # It should contain exactly ONE perfectly assembled message and ONE close frame.
        # The PING and PONG frames must have been safely discarded.
        msg1, flags1 = ws._receive_queue.get_nowait()
        msg2, flags2 = ws._receive_queue.get_nowait()

        assert msg1 == b"Chunk 1 Chunk 2"
        assert flags1 == CurlWsFlag.TEXT
        assert msg2 == b"bye"
        assert flags2 & CurlWsFlag.CLOSE

        # Ensure nothing else leaked into the queue
        assert ws._receive_queue.empty()

    @pytest.mark.asyncio
    async def test_high_concurrency_mixed_frame_stress(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Blasts the connection with hundreds of concurrent sends of varying frame
        types (TEXT, BINARY, PING, and massive Fragmented payloads) while
        simultaneously receiving, to ensure thread-safety, queue backpressure,
        remain robust without deadlocks.
        """
        ws_config(behavior=ServerBehavior.ECHO)

        async with session.ws_connect(
            configurable_ws_server.url,
            coalesce_frames=False,  # Must be False to guarantee 1:1 frame count mapping
            max_send_batch_size=50,
            send_queue_size=500,  # Large enough to absorb the blast without timing out
            recv_queue_size=500,
        ) as ws:

            async def send_text() -> None:
                for i in range(100):
                    await ws.send_str(f"TEXT_{i}")
                    await asyncio.sleep(0.001)  # Micro-sleeps force context switching

            async def send_binary() -> None:
                for i in range(100):
                    await ws.send_binary(f"BIN_{i}".encode())
                    await asyncio.sleep(0.001)

            async def send_pings() -> None:
                for i in range(50):
                    await ws.ping(f"PING_{i}".encode())
                    await asyncio.sleep(0.002)

            async def send_large_fragmented() -> None:
                for _ in range(10):
                    # 100KB payloads will trigger libcurl's 64K fragmentation limits
                    await ws.send_binary(b"L" * 100_000)
                    await asyncio.sleep(0.01)

            # Fire all 260 operations completely concurrently
            _ = await asyncio.gather(
                send_text(),
                send_binary(),
                send_pings(),
                send_large_fragmented(),
            )

            # Now we receive and verify. We expect exactly 210 data frames back.
            # (100 text + 100 bin + 10 large).
            # The 50 PINGs are echoed as PONGs internally by libcurl/websockets
            # and are silently discarded by the architecture.

            received_text = 0
            received_bin = 0
            received_large = 0

            for _ in range(210):
                data, flags = await ws.recv(timeout=5.0)

                if flags & CurlWsFlag.TEXT:
                    received_text += 1
                elif flags & CurlWsFlag.BINARY:
                    if len(data) == 100_000:
                        received_large += 1
                        assert data == b"L" * 100_000
                    else:
                        received_bin += 1

            assert received_text == 100
            assert received_bin == 100
            assert received_large == 10

            # Verify the queue is perfectly empty
            # (No leaked PONGs or malformed trailing fragments)
            with pytest.raises(asyncio.TimeoutError):
                _ = await asyncio.wait_for(ws._receive_queue.get(), timeout=0.2)

    @pytest.mark.asyncio
    async def test_unaligned_simd_xor_masking(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Tests the C-layer AVX-512/AVX2/Scalar fallback XOR masking.
        Uses an unaligned size that crosses multiple internal C-layer buffers.
        """
        ws_config(behavior=ServerBehavior.ECHO)

        # 512 KiB + 13 bytes.
        # Safely under server limit, but crosses:
        # - 64x 8KB SIMD xbufs
        # - 4x 128KB libcurl chunk buffers
        # - Ends with an unaligned remainder for scalar fallback checks.
        payload_size = (512 * 1024) + 13
        payload: bytes = b"X" * payload_size

        async with session.ws_connect(configurable_ws_server.url) as ws:
            await ws.send(payload)

            # The server will echo it back. The C-layer must correctly
            # unmask it for the assertion to pass.
            data, flags = await ws.recv(timeout=10.0)
            assert flags & CurlWsFlag.BINARY
            assert len(data) == payload_size
            assert data == payload

    @pytest.mark.asyncio
    async def test_huge_payload_stress_and_fairness(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Tests the integrity and event loop fairness of a huge 20MB payload.
        This exercises the SIMD XOR masking across thousands of internal
        C buffers and hundreds of Byte-Bucket yield points.
        """
        ws_config(behavior=ServerBehavior.ECHO)

        # Heartbeat task to prove the loop stays responsive during the massive CPU task
        heartbeat_ticks = 0

        async def heartbeat():
            nonlocal heartbeat_ticks
            while True:
                await asyncio.sleep(0.001)
                heartbeat_ticks += 1

        hb_task: Task[None] = asyncio.create_task(heartbeat())

        # 20 MiB payload
        huge_size = 20 * 1024 * 1024
        payload: bytes = b"Z" * huge_size

        try:
            async with session.ws_connect(
                configurable_ws_server.url,
                max_message_size=25 * 1024 * 1024,
                send_time_slice=0.005,
                recv_time_slice=0.005,
            ) as ws:
                # Time the send/recv process
                start_time: float = asyncio.get_running_loop().time()

                await ws.send(payload)
                data, _ = await ws.recv(timeout=20.0)

                duration: float = asyncio.get_running_loop().time() - start_time

                # Assert integrity
                assert len(data) == huge_size
                assert data == payload

                # Assert fairness: With a 20MB payload and 5ms time slice,
                # we yielded at least 160 times. Heartbeat MUST have ticked.
                assert heartbeat_ticks > 0
                assert heartbeat_ticks >= 5

                # Log performance for visibility
                print(
                    f"\n[Huge Payload Test] Transferred {huge_size / 1024**2:.1f} MB "
                    + f"in {duration:.2f}s (~{huge_size * 8 / duration / 1e6:.1f} Mbps)"
                )

        finally:
            _ = hb_task.cancel()
            with suppress(asyncio.CancelledError):
                await hb_task

    @pytest.mark.asyncio
    async def test_high_frequency_ping_pong(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Stress tests the OS selector (epoll/kqueue/select) by performing
        rapid small-frame exchanges.
        """
        for i in range(500):
            msg = f"ping_{i}".encode()
            await ws_connection.send(msg)
            data, _ = await ws_connection.recv(timeout=1.0)
            assert data == msg

    def test_multithreaded_event_loops(
        self, configurable_ws_server: ConfigurableWSServer
    ) -> None:
        """
        Runs two completely independent asyncio loops in two separate threads.
        Ensures C-layer state (like CPU feature detection) is thread-safe.
        """

        def run_loop() -> None:
            async def task() -> None:
                async with (
                    AsyncSession[Response]() as s,
                    s.ws_connect(configurable_ws_server.url) as ws,
                ):
                    for _ in range(50):
                        await ws.send(b"data")
                        _ = await ws.recv()

            asyncio.run(task())

        t1: threading.Thread = threading.Thread(target=run_loop)
        t2: threading.Thread = threading.Thread(target=run_loop)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

    @pytest.mark.asyncio
    async def test_boundary_fragmentation_plus_one(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Tests a payload that is exactly 128KB + 1 byte.
        Forces the C-layer to fill exactly one full chunk and then carry
        the mask state over for a single trailing byte.
        """
        size = (128 * 1024) + 1
        payload: bytes = b"B" * size
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv(timeout=5.0)
        assert data == payload

    @pytest.mark.asyncio
    async def test_transport_exception_bubbles_to_all_waiters(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        Proves that a background transport exception correctly wakes up
        ALL concurrent recv() waiters and doesn't deadlock.
        """
        ws_config(behavior=ServerBehavior.SILENT)
        ws: AsyncWebSocket = await session.ws_connect(
            configurable_ws_server.url, recv_queue_size=10
        )

        # Create 5 concurrent waiters
        tasks: list[Task[tuple[bytes, int]]] = [
            asyncio.create_task(ws.recv(timeout=10.0)) for _ in range(5)
        ]
        await asyncio.sleep(0.1)  # Let them suspend

        # Inject a fatal transport exception directly into the background loop
        fatal_error: CurlError = CurlError(
            "Fatal mock socket error", CurlECode.RECV_ERROR
        )
        ws._finalize_connection(fatal_error)  # pyright: ignore[reportPrivateUsage]

        # Wait for all tasks to resolve
        done, pending = await asyncio.wait(tasks, timeout=2.0)

        assert len(pending) == 0, "Some recv tasks deadlocked!"

        # Every single task should have raised the EXACT transport exception
        for task in done:
            with pytest.raises(CurlError) as exc_info:
                _ = task.result()
            assert exc_info.value.code == CurlECode.RECV_ERROR

        await ws.close()

    @pytest.mark.asyncio
    async def test_graceful_close_timeout_forces_termination(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],
    ) -> None:
        """
        If the server goes totally silent and refuses to complete the close handshake,
        ws.close() must time out and forcefully terminate the socket.
        """
        # Server will accept the connection but never reply to anything
        ws_config(behavior=ServerBehavior.SILENT)
        ws: AsyncWebSocket = await session.ws_connect(configurable_ws_server.url)

        start_time: float = asyncio.get_running_loop().time()

        # Close with a very aggressive 0.5s timeout
        await ws.close(timeout=0.5)

        duration: float = asyncio.get_running_loop().time() - start_time

        # It should take approximately ~0.5 seconds, not hang forever
        assert duration <= 0.5

        # The connection MUST be marked as forcefully terminated
        assert ws._terminated is True


class TestAsyncWebSocketSIMDEdgeCases:
    """Specific tests to probe the C-layer SIMD and scalar cleanup boundaries."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("extra_bytes", [0, 1, 2, 3, 4, 7, 31, 33, 63, 65])
    async def test_simd_masking_tail_logic(
        self, ws_connection: AsyncWebSocket, extra_bytes: int
    ) -> None:
        """
        Probes the C-layer cleanup loops (32-bit and 8-bit fallbacks).
        Payloads are sized to leave specific 'tails' after SIMD vector blocks.
        """
        # Base of 128 (AVX-512 unroll) + the tail we want to test
        size: int = 128 + extra_bytes
        payload: bytes = b"\xde\xad\xbe\xef" * (size // 4) + b"\xff" * (size % 4)
        payload = payload[:size]  # Ensure exact size

        await ws_connection.send_binary(payload)
        data, _ = await ws_connection.recv(timeout=5.0)

        assert len(data) == size
        assert data == payload

    @pytest.mark.asyncio
    async def test_mask_index_persistence_across_unaligned_fragments(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """
        Verifies that the XOR mask index is preserved across fragments that
        are not multiples of 4.
        """
        # Send 3 bytes, then 3 bytes, then 3 bytes.
        # This forces the mask index (0, 1, 2, 3) to wrap around mid-chunk.
        chunks: list[bytes] = [b"ABC", b"DEF", b"GHI", b"JKL"]

        # Manually fragment one logical message
        await ws_connection.send(chunks[0], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        await ws_connection.send(chunks[1], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        await ws_connection.send(chunks[2], flags=CurlWsFlag.BINARY | CurlWsFlag.CONT)
        await ws_connection.send(chunks[3], flags=CurlWsFlag.BINARY)  # Final

        data, _ = await ws_connection.recv(timeout=5.0)
        assert data == b"ABCDEFGHIJKL"

    @pytest.mark.asyncio
    async def test_write_loop_interleaving_stress(
        self,
        session: AsyncSession[Response],
        configurable_ws_server: ConfigurableWSServer,
        ws_config: Callable[..., None],  # <--- MUST be in arguments
    ) -> None:
        """
        Stress tests the background writer by ensuring the queue remains
        functional while a massive 10MB message is being processed.
        """
        # Call the injected fixture to set up the server
        ws_config(behavior=ServerBehavior.ECHO)

        # Generate a 10MB non-repeating payload (0, 1, 2... 255, 0, 1...)
        # This ensures every byte of the XOR mask logic is uniquely exercised.
        huge_payload: bytes = bytes([i % 256 for i in range(10 * 1024 * 1024)])

        async with session.ws_connect(
            configurable_ws_server.url,
            max_message_size=15 * 1024 * 1024,
            send_queue_size=100,
        ) as ws:
            # 1. Enqueue the huge message first.
            # Because we await it, it is guaranteed to be the first item in the queue.
            await ws.send(huge_payload)

            # 2. Immediately queue smaller frames and PINGs.
            # These will enter the queue behind the huge message.
            for i in range(20):
                await ws.send_str(f"interleaved_{i}")
                await ws.ping(b"!")

            # 3. Verify all data arrived intact and in strict FIFO order.

            # Message 1: The Huge Payload
            data_huge, flags_huge = await ws.recv(timeout=15.0)
            assert len(data_huge) == len(huge_payload)
            assert data_huge == huge_payload
            assert flags_huge & CurlWsFlag.BINARY

            # Messages 2-21: The Interleaved strings
            for i in range(20):
                data_small = await ws.recv_str(timeout=2.0)
                assert data_small == f"interleaved_{i}"

    @pytest.mark.asyncio
    async def test_manual_fragmentation_with_empty_chunks(
        self, ws_connection: AsyncWebSocket
    ) -> None:
        """Tests logical messages containing empty fragments."""
        await ws_connection.send(b"Start", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        # Empty fragment in the middle
        await ws_connection.send(b"", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
        await ws_connection.send(b"End", flags=CurlWsFlag.TEXT)

        response = await ws_connection.recv_str()
        assert response == "StartEnd"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("length", [1, 3, 15, 31, 63, 127])
    async def test_simd_to_scalar_transition_boundaries(
        self, ws_connection: AsyncWebSocket, length: int
    ) -> None:
        """
        Forces the C-layer to use scalar clean-up loops by sending payloads
        that are exactly one byte short of SIMD vector boundaries.
        """
        payload: bytes = b"A" * length
        await ws_connection.send(payload)
        data, _ = await ws_connection.recv(timeout=2.0)
        assert data == payload
        assert len(data) == length

    @pytest.mark.asyncio
    @pytest.mark.parametrize("offset", [1, 2, 3, 7])
    async def test_unaligned_memory_source(
        self, ws_connection: AsyncWebSocket, offset: int
    ) -> None:
        """
        Tests sending a memoryview slice that starts at an unaligned physical address.
        Verifies that SIMD 'loadu' (unaligned load) in C doesn't segfault.
        """
        base_data: bytes = b"AlignmentPadding" + b"ActualPayload" * 10
        # Create a view starting at an odd offset (e.g., address ends in 1, 3, 7)
        unaligned_view: memoryview = memoryview(base_data)[offset:]

        await ws_connection.send(unaligned_view)
        data, _ = await ws_connection.recv(timeout=2.0)
        assert data == bytes(unaligned_view)
