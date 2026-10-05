WebSockets
**********

``curl_cffi`` provides high-performance WebSocket clients for synchronous and asynchronous contexts.

Both clients are powered by a heavily optimized, SIMD-accelerated libcurl build capable of multi-gigabit throughput. The synchronous client provides a simple, direct blocking interface alongside an optional event-driven callback loop, while the asynchronous client utilizes an efficient non-blocking I/O architecture.

.. contents:: Table of Contents
   :local:
   :depth: 2
   :backlinks: none

Quick Start
===========

The recommended way to connect to a WebSocket is via the ``Session`` or ``AsyncSession`` context managers.

Sync client:

.. code-block:: python

   from curl_cffi import Session

   with Session() as session:
       with session.ws_connect("wss://ws.postman-echo.com/raw") as ws:
           ws.send_str("Hello, World!")
           print(ws.recv_str())  # Hello, World!


Async client:

.. code-block:: python

   import asyncio
   from curl_cffi import AsyncSession

   async def main():
       async with AsyncSession() as session:
           async with session.ws_connect("wss://ws.postman-echo.com/raw") as ws:
               await ws.send_str("Hello, World!")
               print(await ws.recv_str())  # Hello, World!

Client Selection
================

Both clients send and receive the same messages and share the same timeouts and error handling. The difference is how they perform I/O.

.. list-table::
   :width: 100%
   :header-rows: 1
   :widths: 22 39 39

   * -
     - Synchronous
     - Asynchronous
   * - Class
     - ``WebSocket``
     - ``AsyncWebSocket``
   * - Opened with
     - ``Session.ws_connect()``
     - ``AsyncSession.ws_connect()``
   * - How I/O works
     - Each call blocks until it finishes or times out
     - Background tasks read and write through queues
   * - Send while receiving
     - No, one thread at a time
     - Yes
   * - Event callbacks
     - Yes, with ``run_forever()``
     - No
   * - Good fit for
     - Scripts and simple request/reply exchanges
     - Long-lived streams that send and receive at once

.. tip::

   If your application already uses ``asyncio``, use the asynchronous client. It's also the right choice whenever you need to send and receive at the same time.

Synchronous Client
==================

The synchronous ``WebSocket`` provides a traditional blocking interface. Method calls like ``recv()`` and ``send()`` will block the current thread until the network operation completes or times out.

Connecting
----------

Use ``ws_connect`` from a ``Session``. This method accepts the same network parameters as standard HTTP requests, including impersonation, proxies, and cookies.

.. code-block:: python

    with Session() as session:
        # Session cookies are automatically injected into the WebSocket handshake
        session.cookies.set("session_id", "xyz")

        # Context manager (recommended)
        with session.ws_connect(
            "wss://api.example.com/v1/stream",
            impersonate="chrome",
            proxies={"all": "socks5h://localhost:9050"},
            timeout=10  # Connection phase timeout
        ) as ws:
            pass

        # Manual lifecycle management
        ws = session.ws_connect("wss://api.example.com")
        ws.send_str("Hello")
        ws.close()  # Explicit Close is required

Sending & Receiving
-------------------

All sending and receiving methods are blocking. Sending methods return the number of bytes successfully written to the socket.

.. code-block:: python

    # Send data
    ws.send_str("Hello", timeout=5.0)
    ws.send_bytes(b"\x00\x01\x02")
    ws.send_json({"action": "subscribe"}, timeout=5.0)

    # Receive data (decodes utf-8 automatically)
    msg = ws.recv_str(timeout=5.0)

    # Receive parsed JSON
    data = ws.recv_json()

``recv()`` gives you the message exactly as it arrived, with no UTF-8 validation. Use ``recv_str()`` or ``recv_json()`` if you need that check.

Event Callbacks & run_forever()
-------------------------------

For applications that prefer an event-driven approach, the synchronous client supports callbacks and a blocking ``run_forever()`` loop.

.. code-block:: python

    def on_message(ws: WebSocket, message: bytes | str):
        print(f"Received: {message}")

    def on_error(ws: WebSocket, error: Exception):
        # CurlError for transport errors, Exception for callbacks.
        print(f"Error: {error}")

    def on_open(ws: WebSocket):
        print("Connection open")

    def on_close(ws: WebSocket, close_code: int, close_reason: str):
        print(f"Connection closed: {close_reason}")

    with Session() as session:
        with session.ws_connect(
            "wss://echo.websocket.org",
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        ) as ws:
            ws.send_str("Hello World!")

            # Blocks the thread and dispatches events as they arrive
            ws.run_forever()

These callbacks are only dispatched by ``run_forever()`` — they don't fire for direct ``send()`` / ``recv()`` use.

Thread Safety
-------------

A synchronous ``WebSocket`` is **not thread-safe**. It wraps a single libcurl easy handle, and calling ``send()`` in one thread while another is blocked in ``recv()`` can corrupt libcurl's internal state, leading to undefined behaviour or a segmentation fault.

To send and receive at the same time, use the asynchronous client.

Asynchronous Client
===================

The ``AsyncWebSocket`` client uses a highly optimized **non-blocking I/O Architecture**:

1.  **Outgoing**: Messages are queued for immediate delivery. A background task handles the actual network transmission.
2.  **Incoming**: A background task continuously reads from the network and populates a receive queue, separating your application logic from network speeds.

Connecting
----------

Use the ``ws_connect`` context manager from an ``AsyncSession``.

.. code-block:: python

    async with AsyncSession() as session:
        async with session.ws_connect("wss://api.example.com/v1/stream") as ws:
            ...

These connection styles are also supported:

.. code-block:: python

    # Manual connection management
    ws = await session.ws_connect("wss://api.example.com")
    await ws.send_str("Hello")
    await ws.close()  # Explicit Close is required

    # Same as context manager, alternate style
    async with await session.ws_connect("wss://api.example.com") as ws:
        await ws.send_str("Hello")

Sending Data
------------

Because sending is queued, these methods return immediately unless the internal send queue is full (backpressure).

Async send methods return ``None`` rather than the sent byte-count.

.. code-block:: python

    # Queues data for immediate delivery
    await ws.send_str("Hello")
    await ws.send_json({"action": "subscribe"})

**Flushing:**
If the application logic requires confirmation that messages have been successfully handed off to the underlying network socket, use ``flush()``.

.. code-block:: python

    await ws.send_str("Critical Data")
    await ws.flush()  # Waits until all queued messages are transmitted

Receiving Data
--------------

Concurrent calls to receive methods are fully supported. Messages are distributed to waiters in FIFO order.

.. code-block:: python

    # Receive as string
    msg = await ws.recv_str(timeout=5.0)

    # Iteration (yields raw bytes)
    async for message in ws:
        print(message.decode("utf-8"))

    # Receive raw binary and flags
    payload, flags = await ws.recv(timeout=5.0)  # Omit 'await' in Sync
    if flags & CurlWsFlag.BINARY:
        print(f"Received binary data: {payload}")

``recv()`` gives you the payload exactly as it arrived, with no UTF-8 validation. Use ``recv_str()`` or ``recv_json()`` if you need that check.

Shared Features
===============

The following capabilities are shared equally across both the Synchronous and Asynchronous clients.

Timeouts
--------

All message receive and send operations (e.g., ``recv_str()``, ``send_json()``, ``ping()``) accept an optional ``timeout`` parameter, in seconds. Pass it by keyword; ``AsyncWebSocket.send()`` also accepts its existing positional timeout argument.

.. code-block:: python

    from curl_cffi import WebSocketTimeout

    try:
        # Omit 'await' for sync
        data = await ws.recv_json(timeout=5.0)

    except WebSocketTimeout:
        print("No message received in 5 seconds")

Receive timeouts apply to waiting for a complete message, including the time between fragments. A timeout preserves the partial message for a subsequent ``recv()`` call. This differs from custom fragment loops that ignore the deadline once the first fragment arrives.

An interrupted synchronous send closes the connection because libcurl may have buffered part of a frame, even if it has not reported sending any payload bytes. Reconnect before sending another message.

In ``Session.ws_connect()`` and ``AsyncSession.ws_connect()``, setting ``timeout=None`` is not honoured for the initial connection handshake. The connection phase runs inside libcurl and cannot be interrupted once started, so ``None`` is clamped to 30 seconds. Pass an explicit ``timeout`` if you need a different ceiling.

Heartbeats and Pings
--------------------

When a PING frame is received from the server, libcurl automatically sends a PONG frame in response. Received PONG frames are consumed internally and not delivered to your application.

Libcurl queues automatic PONGs alongside outgoing messages, so a busy sender can delay it.

To send a manual PING frame:

.. code-block:: python

    # Omit 'await' for sync
    await ws.ping(b"keepalive")

    # Zero-length payload is valid
    await ws.ping()

Server pings are automatically replied, but unsolicited PONGs can be sent as a unidirectional heartbeat:

.. code-block:: python

    # Omit 'await' for sync
    await ws.pong(b"keepalive")
    await ws.pong()

Lifecycle Management
--------------------

Context managers handle closing **automatically**. If you need to manage the lifecycle manually:

.. code-block:: python

    # Graceful shutdown: sends a close frame, waits for queued messages to be sent
    # and tears down afterwards (doesn't wait for server's reply).
    await ws.close(code=1000, message=b"bye") # Omit 'await' in sync

    # Forceful shutdown: cancels all I/O and severs the socket immediately.
    ws.terminate()

These methods are fully idempotent and can be called multiple times.

For asynchronous connections:

-   ``ws.terminate()`` is thread-safe and task-safe.
-   ``ws.close_event`` is an async event that can be awaited for a session closure notification.

Reliability & Retries
---------------------

Both clients support exponential backoff with jitter for retrying transient network read errors. The ``WebSocketRetryStrategy`` dataclass is used to configure the retry policy.

.. code-block:: python

    from curl_cffi import WebSocketRetryStrategy

    # Retry transient read errors up to 5 times
    retry_policy = WebSocketRetryStrategy(
        retry=True,
        count=5
    )

    # Works in both session.ws_connect and async_session.ws_connect
    ws = session.ws_connect(url, ws_retry=retry_policy)

Message Limits
--------------

*   **max_message_size** (default: 4MB): The maximum allowed size for a single received message. Messages larger than this will raise a ``WebSocketError`` and close the connection.

.. code-block:: python

    # Allow large received payloads (e.g. 16MB)
    ws = session.ws_connect(url, max_message_size=16 * 1024 * 1024)

There are no limits on the size of the message that can be sent. Large outbound messages are seamlessly broken down into optimal fragments using the ``CURLWS_CONT`` flag, arriving as a single message to the receiver.

Manual Fragmentation
--------------------

The underlying implementation automatically handles frame fragmentation for large outbound messages.

However, if you are generating data on-the-fly and want to stream it to the server in chunks, you can manually fragment messages using the ``CURLWS_CONT`` flag.

.. warning::

    According to the ``libcurl`` specification, you **must** include the underlying message type (e.g., ``TEXT`` or ``BINARY``) in every chunk, alongside the ``CONT`` flag. The final chunk simply drops the ``CONT`` flag to conclude the message.

    A manually fragmented message occupies the connection until its final chunk. If another task calls ``send()`` in between, the frames interleave and libcurl rejects the message with "fragmented message interrupted". Hold your own lock for the duration of a manually fragmented message, or send it from a single task.

.. code-block:: python

    from curl_cffi import CurlWsFlag

    # Manually fragment across frames (omit 'await' in sync)
    await ws.send("Part 1...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    await ws.send("Part 2...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    await ws.send("Final part", flags=CurlWsFlag.TEXT)

Error Handling
--------------

Network errors are raised as ``CurlError``. WebSocket-specific failures — a closed connection, a timeout, an oversized message — use the ``WebSocketError`` subclasses.

.. code-block:: python

    from curl_cffi import CurlError, WebSocketClosed, WebSocketError, WebSocketTimeout

    try:
        msg = ws.recv_str()  # Add 'await' in Async
    except WebSocketClosed as e:
        print(f"Closed: {e.code} - {e}")
    except WebSocketTimeout:
        print("Did not receive a message in time.")
    except WebSocketError as e:
        print(f"WebSocket specific error: {e}")
    except CurlError as e:
        print(f"Network transport error: {e}")

Async-Only Advanced Configuration
=================================

The ``AsyncWebSocket`` client exposes several advanced configuration options to tune its I/O architecture.

Queue Sizes (Backpressure)
--------------------------

You can control the internal buffer sizes to manage TCP backpressure. These values also influence the maximum possible memory footprint.

*   **recv_queue_size** (default: 64): Max incoming messages to buffer internally. ``max_message_size`` caps how large each one can be, so the worst case is fixed at ``recv_queue_size`` × ``max_message_size`` — 256MB with the defaults.
*   **send_queue_size** (default: 32): Max outgoing messages to buffer before ``send()`` blocks. Outgoing messages have no size limit, so size this against your own largest message.
*   **block_on_recv_queue_full** (default: ``True``): Behavior when the receive queue is full. If ``True``, the reader blocks until there is space in the queue (may cause timeouts). If ``False``, the connection fails immediately to prevent data loss.
*   **drain_on_error** (default: ``False``): When a fatal error occurs, normally it is raised immediately. When this option is enabled, calls to ``recv()`` will yield all buffered messages first before raising the exception.

Queue size interacts with cache residency: the working set is ``queue_size`` × typical message size, and once it exceeds the CPU's L2/L3 cache, throughput drops.

.. code-block:: python

    # Many small messages (< 4KB): larger queues cut scheduling overhead
    ws = await session.ws_connect(url, recv_queue_size=1024, send_queue_size=1024)

    # Streaming large messages (>= 64KB): smaller queues keep the working
    # set in cache and measurably improve throughput
    ws = await session.ws_connect(url, recv_queue_size=16, send_queue_size=16)

Frame Coalescing
----------------

This is an *optional* power-user optimization technique which breaks frame boundaries and concatenates multiple pending messages from the send queue into a single WebSocket frame. This significantly reduces system call overhead and boosts throughput for chatty streams with small payloads.

.. warning::

    Multiple messages will arrive as a single merged payload. Ensure your server application can handle concatenated strings/bytes.

    Large batches share the outgoing queue with automatic PONG replies and can delay them. Lower ``max_send_batch_size`` if your server has a strict ping timeout.

*   **coalesce_frames** (default: ``False``): Enable frame coalescing.
*   **max_send_batch_size** (default: 64): Max messages to merge per frame.

.. code-block:: pycon

    >>> import asyncio
    >>> from curl_cffi import AsyncSession, Response
    >>> async def test_coalescing():
    ...     """Test frame coalescing feature"""
    ...     async with AsyncSession[Response]() as session:
    ...         async with session.ws_connect("wss://ws.postman-echo.com/raw", coalesce_frames=True) as ws:
    ...             # Take advantage of concurrent sends in quick succession
    ...             await asyncio.gather(
    ...                 ws.send_str("Concurrent sending"),
    ...                 ws.send_str(" is "),
    ...                 ws.send_str("so cool!!"),
    ...             )
    ...             response: str = await ws.recv_str()
    ...             print(response)
    ...
    >>> asyncio.run(test_coalescing())
    Concurrent sending is so cool!!

Cooperative Multitasking
------------------------

To adjust event loop fairness during high-volume streams, you can tune the time-based cooperative scheduler:

*   **recv_time_slice** (default: 0.01s): Max time spent processing incoming messages before yielding (10ms).
*   **send_time_slice** (default: 0.01s): Max time spent sending messages before yielding (10ms).

.. code-block:: python

    # Force more frequent yields for lower latency in other tasks (1ms)
    ws = await session.ws_connect(url, recv_time_slice=0.001)

Upgrading from Earlier Versions
===============================

**Auto-Reassembly & recv_fragment**:
The WebSocket clients now handle message fragmentation and reassembly automatically. You are guaranteed to receive complete logical messages when calling ``recv()``, ``recv_str()``, or ``recv_json()``.

Synchronous ``WebSocket.recv_fragment()`` remains available for code that needs raw fragments. It does not wait for socket readiness and can raise ``CurlError`` with ``CurlECode.AGAIN``. Do not mix it with ``recv()`` while a partial message is buffered.

``AsyncWebSocket.recv_fragment()`` remains unsupported. Use ``recv()`` for complete messages; its background reader handles reassembly. Do not call ``Curl.ws_recv()`` on an ``AsyncWebSocket`` managed connection, since that would compete with the background reader. Applications requiring custom fragment handling can manage a low-level ``Curl`` connection themselves.

When migrating a custom fragment loop to ``recv(timeout=...)``, note that its deadline still applies after the first fragment arrives; partial messages are retained after a timeout.

**Closing a session closes its WebSockets**:
Closing a session, or leaving its context manager block, now closes any WebSocket still open on it with a ``1001`` (going away) frame. Keep the session open for as long as the connection is needed.

**WebSockets count against max_clients**:
Each async WebSocket holds one of the ``AsyncSession`` curl handles for its lifetime. If every handle is held by a WebSocket, further requests raise ``RequestException`` rather than waiting indefinitely. Increase ``max_clients`` if you need more connections at once.

**send() timeout**:
Pass ``timeout=`` by name. ``AsyncWebSocket.send(payload, flags, timeout)`` remains supported for compatibility; the new synchronous send timeout is keyword-only.

Performance Tuning
==================

The WebSocket protocol requires every client-to-server message to be masked (XOR) according to RFC 6455.

Curl-CFFI uses a customized build of libcurl enhanced with AVX-512/AVX2/NEON SIMD vectorized masking. It is capable of multi-gigabit throughput in both directions.

If your application needs to send large volumes of data, you should **focus on sending fewer, larger messages** (e.g., 64KB to 1MB per message). This minimizes the framing and FFI overhead, allowing the C-layer to process the payload at hardware limits.
