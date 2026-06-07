WebSockets
**********

``curl_cffi`` provides WebSocket clients for both synchronous and asynchronous contexts.

The asynchronous client (``AsyncWebSocket``) is the recommended choice for most applications. Built for high performance, it offers a rich feature set—including background I/O, configurable backpressure, and automatic retries. All examples in this guide focus on the asynchronous API.

Quick Start
===========

The recommended way to connect to a WebSocket is via the ``AsyncSession``.

.. note::

   **Syntax**: The ``ws_connect`` method supports the standard async context manager syntax.

   **Recommended:** ``async with session.ws_connect(...) as ws:``

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    async def main():
        async with AsyncSession() as session:
            # Connect using the standard context manager syntax
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

Connecting
==========

Use ``ws_connect`` from an ``AsyncSession``. This method accepts the same network parameters as standard HTTP requests.

**Key Features:**

*   **Impersonation**: Use ``impersonate="chrome"`` to mimic browser fingerprints.
*   **Cookies**: Automatically inherits cookies from the ``AsyncSession``, and merges any new cookies passed to the method.
*   **Proxies**: Supports HTTP/HTTPS/SOCKS proxies.

.. code-block:: python

    async with AsyncSession() as session:
        # Session cookies are automatically included
        session.cookies.set("session_id", "xyz")

        async with session.ws_connect(
            "wss://api.example.com/v1/stream",
            impersonate="chrome",
            auth=("user", "pass"),
            params={"stream_id": "123"},
            timeout=10  # Connection timeout
        ) as ws:
            ...

Sending Data
============

Methods for sending data place the message into an outgoing queue. They are generally non-blocking unless the send queue size limit is reached.

.. code-block:: python

    # Send text
    await ws.send_str("Hello")

    # Send bytes
    await ws.send_bytes(b"\x00\x01\x02")

    # Send JSON (automatically serializes dict to JSON string)
    await ws.send_json({"action": "subscribe", "channel": "btc_usd"})

    # Send generic (accepts str, bytes, bytearray, memoryview)
    await ws.send("Auto-detected payload")

Receiving Data
==============

You can receive individual messages or iterate over the connection.

Receive Methods
---------------

All receive methods support an optional ``timeout`` argument (in seconds).

.. code-block:: python

    # Receive as string (decodes utf-8 automatically)
    msg = await ws.recv_str()

    # Receive with a 5-second timeout
    try:
        data = await ws.recv_json(timeout=5.0)
    except WebSocketTimeout:
        print("No message received in 5 seconds")

    # Receive raw bytes and frame flags
    # Useful for inspecting the frame type (e.g., TEXT vs BINARY)
    content, flags = await ws.recv()
    if flags & CurlWsFlag.TEXT:
        text = content.decode("utf-8")

Concurrent calls to receive methods are fully supported. Messages are distributed to waiters in FIFO order, unlike many other libraries that limit consumption to a single task.

.. note::

    ``recv_str()`` and ``recv_json()`` check that the incoming message is a ``TEXT`` frame. If the server sends a ``BINARY`` frame, these methods will raise a ``WebSocketError``.

Async Iteration
---------------

The most pythonic way to consume a stream is iteration.

.. note::

    Iteration yields raw ``bytes``. If you expect text, you must decode it yourself.

.. code-block:: python

    async for message in ws:
        print(message.decode("utf-8"))

Heartbeats and Pings
====================

Libcurl handles incoming PONGs automatically. If you need to send a manual PING frame (e.g., for application-layer keepalives):

.. code-block:: python

    await ws.ping(b"keepalive")

.. note::

    PONG frames are consumed internally and are not delivered to your ``recv()`` calls or async iteration.

Lifecycle Management
====================

Closing
-------

The context manager handles closing automatically. If you need to close manually, there are two methods available:

.. code-block:: python

    # Graceful shutdown: sends a close frame, waits for queued
    # outgoing messages to flush, and awaits server acknowledgment.
    await ws.close(code=1000, message=b"bye")

    # Forceful shutdown: cancels all background I/O tasks and
    # cleans up the socket immediately. Thread-safe and synchronous.
    ws.terminate()

Both methods are idempotent and safe to call multiple times.

Flushing
--------

Because sending is non-blocking, returning from ``await ws.send()`` only guarantees the message was placed in the internal queue. A background task handles the actual network transmission.

If your application logic requires confirmation that messages have been successfully handed off to the underlying network socket before proceeding (e.g., before shutting down the application or triggering a dependent side-effect), use ``flush()``.

.. code-block:: python

    await ws.send_str("Critical Data")
    await ws.flush()  # Awaits until all queued messages are transmitted

Since the background sender sends out the data as soon as it's queued, waiting for the send queue to clear is not usually required.

You can check the size of the send queue by checking the ``send_queue_size`` property.

.. code-block:: python

    print(ws.send_queue_size)

Error Handling
==============

Network errors are raised as ``WebSocketError`` or its subclasses.

.. code-block:: python

    from curl_cffi import WebSocketClosed, WebSocketTimeout, WebSocketError

    try:
        msg = await ws.recv_str()
    except WebSocketClosed as e:
        print(f"Closed: {e.code} - {e.message}")
    except WebSocketTimeout:
        print("Did not receive a message in time.")
    except WebSocketError as e:
        print(f"Transport/Network error: {e}")

Advanced Configuration
======================

The ``AsyncWebSocket`` client is powered by libcurl and tuned for high-performance asyncio applications.

Background I/O Architecture
---------------------------

This implementation uses a background I/O model to ensure high performance:

1.  **Outgoing**: Messages are queued for delivery (non-blocking unless the queue is full).
2.  **Incoming**: A background task continuously reads from the network and populates a receive queue.

This design separates the application logic from network speeds. Even if your code processes messages slowly, the underlying network socket remains unblocked, allowing for maximum concurrency and throughput.

Queue Sizes (Backpressure)
--------------------------

You can control the internal buffer sizes to manage backpressure.

*   **recv_queue_size** (default: 128): Max incoming messages to buffer.
*   **send_queue_size** (default: 128): Max outgoing messages to buffer.
*   **block_on_recv_queue_full** (default: ``True``): The reader pauses when the queue is full (TCP backpressure). If ``False``, the connection will fail instead (``OUT_OF_MEMORY``) to avoid stalling the reader.

.. code-block:: python

    # Increase queues for high-throughput streams (e.g., market data)
    ws = await session.ws_connect(
        url,
        recv_queue_size=512,
        send_queue_size=256
    )

Buffer sizes are a trade-off between latency, bufferbloat and burst absorption capacity.

.. code-block:: python

    # High throughput, fast moving streams (e.g., video)
    ws = await session.ws_connect(
        url,
        recv_queue_size=2048,
        send_queue_size=2048
    )

Message Limits
--------------

*   **max_message_size** (default: 4MB): The maximum allowed size for a single received message. Messages larger than this will raise a ``WebSocketError`` (Too Large) and close the connection.

.. code-block:: python

    # Allow large received payloads (e.g. 16MB)
    ws = await session.ws_connect(url, max_message_size=16 * 1024 * 1024)

There are no limits on the size of the message that can be sent. Large outbound messages are seamlessly broken down into optimal fragments using the ``CURLWS_CONT`` flag, appearing as a single logical message to the server.

Manual Fragmentation
--------------------

The library automatically fragments large payloads for you. If you are generating data on-the-fly and want to stream it to the server in chunks, you can manually fragment messages using the ``CURLWS_CONT`` flag.

.. warning::

    According to the ``libcurl`` specification, you **must** include the underlying message type (e.g., ``TEXT`` or ``BINARY``) in every chunk, alongside the ``CONT`` flag. The final chunk simply drops the ``CONT`` flag to conclude the message.

.. code-block:: python

    from curl_cffi import CurlWsFlag

    # Send the first chunk
    await ws.send("Part 1...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)

    # Send intermediate chunks (Type flag MUST be included)
    await ws.send("Part 2...", flags=CurlWsFlag.TEXT | CurlWsFlag.CONT)

    # Send the final chunk (drops the CONT flag)
    await ws.send("Final part", flags=CurlWsFlag.TEXT)

Frame Coalescing (Throughput)
-----------------------------

For chatty protocols sending many small messages, you can enable **coalescing**. This merges multiple queued message payloads from the send queue into a single transmission batch to reduce syscall overhead.

*   **coalesce_frames** (default: ``False``): Enable batching.
*   **max_send_batch_size** (default: 64): Max messages to merge.

.. code-block:: python

    # Optimize for throughput over latency
    ws = await session.ws_connect(url, coalesce_frames=True)

Reliability & Retries
---------------------

*   **drain_on_error** (default: ``False``): When a network error occurs, ``recv()`` will continue to yield buffered messages in the queue before raising the exception. Helps ensure data integrity on unstable connections.
*   **ws_retry**: A policy object to configure automatic retries on failed message receive operations.

.. code-block:: python

    from curl_cffi import WebSocketRetryStrategy

    # Retry transient read errors up to 5 times
    retry_policy = WebSocketRetryStrategy(
        retry=True,
        count=5
    )

    ws = await session.ws_connect(
        url,
        drain_on_error=True,
        ws_retry=retry_policy
    )

Cooperative Multitasking
------------------------

To prevent the background I/O tasks from starving the asyncio event loop during heavy load, you can tune the time slicing.

*   **recv_time_slice** (default: 0.01s): Max time spent processing incoming messages before yielding (10ms).
*   **send_time_slice** (default: 0.005s): Max time spent sending messages before yielding (5ms).

.. code-block:: python

    # Force more frequent yields for lower latency in other async tasks
    ws = await session.ws_connect(url, recv_time_slice=0.001)

Performance Tuning
==================

The ``curl_cffi`` WebSocket implementation uses a patched version of libcurl enhanced with AVX-512/AVX2/NEON SIMD **hardware acceleration**. It is capable of multi-gigabit throughput.

If your application needs to push a massive volume of data (e.g., file uploads, video streaming, or bulk syncing), **you should focus on sending fewer, larger messages rather than many small messages.**

*   **The Overhead:** The WebSocket protocol requires every client-to-server message to be masked (XOR) for security. Additionally, every call to ``await ws.send()`` carries a small asyncio overhead.
*   **The Solution:** Increase queue sizes and condense your data into larger blocks (e.g., 64KB to 1MB per message) before sending. This drastically reduces the framing, masking, and FFI overhead, allowing libcurl to process the data at maximum speed.

Automatic Reassembly
--------------------

You never need to worry about network fragmentation. If you send or receive a huge message, the underlying engine automatically chunks it into optimal network frames for transmission, and seamlessly reassembles those frames on the other side.

Your application will always receive the data exactly as it was sent — as a single, complete string or bytes.
