WebSockets
**********

``curl_cffi`` provides high-performance WebSocket clients for synchronous and asynchronous contexts.

Both clients are powered by a heavily optimized, SIMD-accelerated libcurl build capable of multi-gigabit throughput. The synchronous client provides a simple, direct blocking interface alongside an optional event-driven callback loop, while the asynchronous client utilizes an efficient non-blocking I/O architecture.

.. contents:: Table of Contents
   :local:
   :depth: 2

Quick Start
===========

The recommended way to connect to a WebSocket is via the ``Session`` or ``AsyncSession`` context managers.

Sync Quick Start
----------------

.. code-block:: python

    from curl_cffi import Session

    def main():
        with Session() as session:
            # Connect using the standard context manager syntax
            with session.ws_connect("wss://echo.websocket.org") as ws:

                # Send a text message
                ws.send_str("Hello, World!")

                # Receive a text message
                msg = ws.recv_str()
                print(f"Received: {msg}")

                # Iterate over messages
                for message in ws:
                    print(f"Stream: {message}")

    if __name__ == "__main__":
        main()

Async Quick Start
-----------------

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    async def main():
        async with AsyncSession() as session:
            # Connect using the async context manager syntax
            async with session.ws_connect("wss://echo.websocket.org") as ws:

                # Send a text message
                await ws.send_str("Hello, World!")

                # Receive a text message
                msg = await ws.recv_str()
                print(f"Received: {msg}")

                # Iterate over messages
                async for message in ws:
                    print(f"Stream: {message}")

    asyncio.run(main())

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

``recv()`` gives you the payload exactly as it arrived, with no UTF-8 validation. Use ``recv_str()`` or ``recv_json()`` if you need that check.

Event Callbacks & run_forever()
-------------------------------

For applications that prefer an event-driven approach over manual iteration, the synchronous client supports callbacks and a blocking ``run_forever()`` loop.

.. code-block:: python

    def on_message(ws, message):
        print(f"Received: {message}")

    def on_error(ws, error):
        print(f"Error: {error}")

    def on_close(ws, close_code, close_reason):
        print("Connection closed")

    with Session() as session:
        with session.ws_connect(
            "wss://echo.websocket.org",
            on_message=on_message,
            on_error=on_error,
            on_close=on_close
        ) as ws:
            ws.send_str("Hello World!")

            # Blocks the thread and dispatches events as they arrive
            ws.run_forever()

Thread Safety
-------------

The synchronous ``WebSocket`` relies on ``libcurl`` easy handles, which is **not thread-safe** at the C level. If Thread A is blocked in ``recv()``, and Thread B concurrently calls ``send()``, libcurl's internal state machine can corrupt, leading to undefined behavior or segmentation faults.

For concurrent, full-duplex streaming, using the **AsyncWebSocket** is the best option.

Asynchronous Client
===================

The ``AsyncWebSocket`` client uses a highly optimized **non-blocking I/O Architecture**:

1.  **Outgoing**: Messages are queued for delivery instantly. A background task handles the actual network transmission.
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

All receive and send operations (e.g., ``recv_str()``, ``send_json()``, ``ping()``) accept an optional keyword-only ``timeout`` argument in seconds.

.. code-block:: python

    from curl_cffi import WebSocketTimeout

    try:
        # Async
        data = await ws.recv_json(timeout=5.0)

        # Sync
        data = ws.recv_json(timeout=5.0)

    except WebSocketTimeout:
        print("No message received in 5 seconds")

Heartbeats and Pings
--------------------

When a PING frame is received from the server, libcurl automatically sends a PONG frame in response. Received PONG frames are consumed internally and not delivered to your application.

The automatic PONG is queued alongside your own outgoing messages, so a busy sender can delay it. Worth knowing if your server enforces a tight ping deadline.

To send a manual PING frame:

.. code-block:: python

    # Async
    await ws.ping(b"keepalive")

    # Sync
    ws.ping(b"keepalive")

Lifecycle Management
--------------------

Context managers handle closing **automatically**. If you need to manage the lifecycle manually:

.. code-block:: python

    # Graceful shutdown: sends a close frame, waits for queued messages,
    # and awaits server acknowledgment.
    await ws.close(code=1000, message=b"bye") # Omit 'await' in Sync

    # Forceful shutdown: cancels all I/O and severs the socket immediately.
    ws.terminate()

These methods are fully idempotent and can be called multiple times.

For asynchronous connections:

-   ``ws.terminate()`` is thread-safe and task-safe.
-   ``ws.close_event`` is an async event that can be awaited for a session closure notification.

Reliability & Retries
---------------------

Both clients support automatic exponential backoff retries with jitter for transient network read errors.

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

There are no limits on the size of the message that can be sent. Large outbound messages are seamlessly broken down into optimal fragments using the ``CURLWS_CONT`` flag.

Manual Fragmentation
--------------------

You do not need to worry about frame fragmentation for large payloads. However, if you are generating data on-the-fly and want to stream it to the server in chunks, you can manually fragment messages using the ``CURLWS_CONT`` flag.

.. warning::

    According to the ``libcurl`` specification, you **must** include the underlying message type (e.g., ``TEXT`` or ``BINARY``) in every chunk, alongside the ``CONT`` flag. The final chunk simply drops the ``CONT`` flag to conclude the message.

.. code-block:: python

    from curl_cffi import CurlWsFlag

    # Async
    await ws.send("Part 1...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    await ws.send("Part 2...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    await ws.send("Final part", flags=CurlWsFlag.TEXT)

    # Sync
    ws.send("Part 1...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    ws.send("Part 2...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)
    ws.send("Final part", flags=CurlWsFlag.TEXT)

Error Handling
--------------

Network errors are raised as ``WebSocketError`` or its subclasses.

.. code-block:: python

    from curl_cffi import WebSocketClosed, WebSocketTimeout, WebSocketError

    try:
        msg = ws.recv_str() # Add 'await' in Async
    except WebSocketClosed as e:
        print(f"Closed: {e.code} - {e}")
    except WebSocketTimeout:
        print("Did not receive a message in time.")
    except WebSocketError as e:
        print(f"Transport/Network error: {e}")

Async-Only Advanced Configuration
=================================

The ``AsyncWebSocket`` client exposes several advanced configuration options to tune its Background I/O architecture.

Queue Sizes (Backpressure)
--------------------------

You can control the internal buffer sizes to manage TCP backpressure. These values also influence the maximum possible memory footprint.

*   **recv_queue_size** (default: 64): Max incoming messages to buffer internally. ``max_message_size`` caps how large each one can be, so the worst case is fixed at ``recv_queue_size`` × ``max_message_size`` — 256MB with the defaults.
*   **send_queue_size** (default: 32): Max outgoing messages to buffer before ``send()`` blocks. Outgoing messages have no size limit, so size this against your own largest message.
*   **block_on_recv_queue_full** (default: ``True``): Behavior when the receive queue is full. If ``True`` (default), the reader blocks until there is space in the queue (may cause timeouts). If ``False``, the connection fails immediately to prevent data loss.
*   **drain_on_error** (default: ``False``): When a fatal error occurs, calls to ``recv()`` will drain all buffered messages first before raising the exception.

.. code-block:: python

    # Larger queues suit high rates of small messages (e.g., market data)
    ws = await session.ws_connect(
        url,
        recv_queue_size=1024,
        send_queue_size=1024
    )

Frame Coalescing
----------------

This is an *optional* optimization technique which merges multiple pending messages from the send queue into a single WebSocket frame. This significantly reduces system call overhead and boosts throughput for chatty streams.

.. warning::

    Multiple messages will arrive as a single concatenated payload. Ensure your server protocol expects concatenated strings/bytes.

    Large batches share the outgoing queue with automatic PONG replies and can delay them. Lower ``max_send_batch_size`` if your server has a strict ping timeout.

*   **coalesce_frames** (default: ``False``): Enable batching.
*   **max_send_batch_size** (default: 64): Max messages to merge per frame.

.. code-block:: pycon

    >>> import asyncio
    >>> from curl_cffi import AsyncSession, Response
    >>> async def test_coalescing():
    ...     """Test frame coalescing feature"""
    ...     async with AsyncSession[Response]() as session:
    ...         async with session.ws_connect("wss://ws.postman-echo.com/raw", coalesce_frames=True) as ws:
    ...             # Take advantage of concurrent sends in quick succession
    ...             async with asyncio.TaskGroup() as tg:
    ...                 tg.create_task(ws.send_str("Concurrent sending"))
    ...                 tg.create_task(ws.send_str(" is "))
    ...                 tg.create_task(ws.send_str("so cool!!"))
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

As a result, the ``recv_fragment()`` method has been deprecated and removed. If your existing code relied on ``recv_fragment()`` to manually stitch together ``CONT`` frames, you can safely remove that logic and simply call ``recv()``.

**Closing a session closes its WebSockets**:
Closing an ``AsyncSession``, or leaving its ``async with`` block, now closes any WebSocket still open on it with a ``1001`` (going away) frame. Keep the session open for as long as the connection is needed.

**WebSockets count against max_clients**:
Each WebSocket holds one of the session's curl handles for as long as it stays connected. If every handle is held by a WebSocket, further requests raise ``RequestException`` rather than waiting indefinitely. Increase ``max_clients`` if you need more connections at once.

**send() timeout is keyword-only**:
``ws.send(payload, flags, timeout)`` no longer works — pass ``timeout=`` by name. This matches every other send and receive method.

Performance Tuning
==================

The WebSocket protocol requires every client-to-server message to be masked (XOR) according to RFC 6455.

Curl-CFFI uses a highly customized version of libcurl enhanced with AVX-512/AVX2/NEON SIMD vectorized masking. It is capable of multi-gigabit throughput in both directions.

If your application needs to send large volumes of data, you should **focus on sending fewer, larger messages** (e.g., 64KB to 1MB per message). This minimizes the framing and FFI overhead, allowing the C-layer SIMD instructions to process the payload at hardware limits.
