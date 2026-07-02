WebSockets
**********

``curl_cffi`` provides high-performance WebSocket clients for both synchronous and asynchronous contexts.

Both clients are powered by a heavily optimized, SIMD-accelerated C extension capable of multi-gigabit throughput. The asynchronous client utilizes a background I/O architecture for non-blocking performance, while the synchronous client provides a simple, direct blocking interface alongside an optional event-driven callback loop.

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

        with session.ws_connect(
            "wss://api.example.com/v1/stream",
            impersonate="chrome",
            proxies={"all": "socks5h://localhost:9050"},
            timeout=10  # Connection phase timeout
        ) as ws:
            pass

Sending & Receiving
-------------------

All sending and receiving methods are blocking. Sending methods return the number of bytes successfully written to the socket.

.. code-block:: python

    # Send data
    ws.send_str("Hello", timeout=5.0)
    ws.send_bytes(b"\x00\x01\x02")
    ws.send_json({"action": "subscribe"})

    # Receive data (decodes utf-8 automatically)
    msg = ws.recv_str(timeout=5.0)

    # Receive parsed JSON
    data = ws.recv_json()

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

Asynchronous Client
===================

The ``AsyncWebSocket`` client uses a highly optimized **Background I/O Architecture**:

1.  **Outgoing**: Messages are queued for delivery instantly (non-blocking). A background task handles the actual network transmission.
2.  **Incoming**: A background task continuously reads from the network and populates a receive queue, separating your application logic from network speeds.

Connecting
----------

Use ``ws_connect`` from an ``AsyncSession``.

.. code-block:: python

    async with AsyncSession() as session:
        async with session.ws_connect("wss://api.example.com/v1/stream") as ws:
            pass

Sending Data
------------

Because sending is queued, these methods return immediately unless the internal send queue is full (backpressure).

.. code-block:: python

    # Queues data for background delivery
    await ws.send_str("Hello")
    await ws.send_json({"action": "subscribe"})

**Flushing**
If your application logic requires confirmation that messages have been successfully handed off to the underlying network socket before proceeding, use ``flush()``.

.. code-block:: python

    await ws.send_str("Critical Data")
    await ws.flush()  # Awaits until all queued messages are transmitted

Receiving Data
--------------

Concurrent calls to receive methods are fully supported. Messages are distributed to waiters in FIFO order.

.. code-block:: python

    # Receive as string
    msg = await ws.recv_str(timeout=5.0)

    # Iteration (yields raw bytes)
    async for message in ws:
        print(message.decode("utf-8"))


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

    According to the RFC, you **must** include the underlying message type (e.g., ``TEXT`` or ``BINARY``) in every chunk, alongside the ``CONT`` flag. The final chunk simply drops the ``CONT`` flag to conclude the message.

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
        print(f"Closed: {e.code} - {e.message}")
    except WebSocketTimeout:
        print("Did not receive a message in time.")
    except WebSocketError as e:
        print(f"Transport/Network error: {e}")

Async-Only Advanced Configuration
=================================

The ``AsyncWebSocket`` client exposes several advanced configuration options to tune its Background I/O architecture.

Queue Sizes (Backpressure)
--------------------------

You can control the internal buffer sizes to manage TCP backpressure.

*   **recv_queue_size** (default: 64): Max incoming messages to buffer internally.
*   **send_queue_size** (default: 32): Max outgoing messages to buffer before ``send()`` blocks.
*   **block_on_recv_queue_full** (default: ``True``): The background reader pauses when the receive queue is full. When set to ``False``, the connection will fail immediately to avoid silent data loss.
*   **drain_on_error** (default: ``False``): When a fatal error occurs, calls to ``recv()`` will yield all buffered messages first before raising the exception.

.. code-block:: python

    # Increase queues for high-throughput fast-moving streams (e.g., video/market data)
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

To adjust event loop fairness during extremely high-volume streams, you can tune the time-based cooperative scheduler:

*   **recv_time_slice** (default: 0.01s): Max time spent processing incoming messages before yielding (10ms).
*   **send_time_slice** (default: 0.01s): Max time spent sending messages before yielding (10ms).

.. code-block:: python

    # Force more frequent yields for lower latency in other tasks (1ms)
    ws = await session.ws_connect(url, recv_time_slice=0.001)

Performance Tuning
==================

The WebSocket protocol requires every client-to-server message to be masked (XOR) according to RFC 6455.

Curl-CFFI uses a highly customized version of libcurl enhanced with AVX-512/AVX2/NEON SIMD vectorized masking. It is capable of multi-gigabit throughput in both directions.

If your application needs to send massive volumes of data, you should **focus on sending fewer, larger messages** (e.g., 64KB to 1MB per message). This minimizes the framing and FFI overhead, allowing the C-layer SIMD instructions to process the payload at hardware limits.
