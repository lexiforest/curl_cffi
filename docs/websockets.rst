WebSockets
**********

``curl_cffi`` provides WebSocket clients for both synchronous and asynchronous contexts.

.. important::

   **Recommendation: Use Async**

   The asynchronous implementation (``AsyncWebSocket``) is significantly more developed, robust, and feature-rich than the synchronous version. It features a **decoupled I/O model** (background readers/writers), flow control, configurable backpressure, and automatic retries.

   Unless you are strictly bound to a synchronous environment, we strongly recommend using the **Async** API described below for all use cases.

Async WebSockets
================

The ``AsyncWebSocket`` client is powered by libcurl and tuned for high-performance asyncio applications. It supports standard features like text/binary frames, pings, and automatic handling of control frames.

**Architecture**

The implementation uses a **decoupled I/O model**:

1.  **Sending** puts messages into a queue (non-blocking unless the queue is full).
2.  **Receiving** pulls from a queue populated by a dedicated background task.

This ensures high concurrency and prevents slow processing logic from blocking the underlying network socket (ping/pongs).

Quick Start
===========

The recommended way to use WebSockets is via the ``AsyncSession``.

.. warning::

   **Syntax**: ``ws_connect`` is an asynchronous factory method.
   You must ``await`` the connection call *before* entering the context manager.

   **Correct:** ``async with await s.ws_connect(...) as ws:``

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    async def main():
        async with AsyncSession() as s:
            # Note the syntax: await s.ws_connect(...)
            async with await s.ws_connect("wss://echo.websocket.org") as ws:

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

    async with AsyncSession() as s:
        # Session cookies are automatically included
        s.cookies.set("session_id", "xyz")

        async with await s.ws_connect(
            "wss://api.example.com/v1/stream",
            impersonate="chrome",
            auth=("user", "pass"),
            params={"stream_id": "123"},
            timeout=10  # Connection timeout
        ) as ws:
            ...

Sending Data
============

Methods for sending data place the message into an outgoing queue. They are generally non-blocking unless the ``send_queue_size`` limit is reached.

.. code-block:: python

    # Send text
    await ws.send_str("Hello")

    # Send bytes
    await ws.send_bytes(b"\x00\x01\x02")

    # Send JSON (automatically serializes dict to JSON string)
    await ws.send_json({"action": "subscribe", "channel": "btc_usd"})

    # Send generic (accepts str, bytes, bytearray, memoryview)
    await ws.send("Auto-detected payload")

**Pings**

Libcurl handles Pongs automatically, but you can send a manual Ping frame if needed (e.g., application-layer keepalive).

.. code-block:: python

    await ws.ping(b"keepalive")

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
    # Useful for inspecting frame types (e.g., checking for CONTINUATION flags)
    content, flags = await ws.recv()

Async Iteration
---------------

The most pythonic way to consume a stream is iteration.

.. note::

    Iteration yields ``bytes``. If you expect text, you must decode it yourself.

.. code-block:: python

    async for chunk in ws:
        print(chunk.decode("utf-8"))

Lifecycle Management
====================

Closing
-------

The context manager handles closing automatically. If you need to close manually:

.. code-block:: python

    await ws.close()
    # Or with a custom code/reason
    await ws.close(code=1000, message=b"bye")

Flushing
--------

Because ``send()`` is decoupled from the network, returning from ``await send()`` only means the message is queued. Use ``flush()`` to ensure all queued messages have effectively been written to the socket.

.. code-block:: python

    await ws.send_str("Critical Data")
    await ws.flush()  # Blocks until the send queue is empty

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

The ``AsyncWebSocket`` implementation allows fine-tuning for high-performance scenarios.

Queue Sizes (Backpressure)
--------------------------

You can control the internal buffer sizes to manage backpressure.

*   **recv_queue_size** (default: 32): Max incoming messages to buffer.
*   **send_queue_size** (default: 16): Max outgoing messages to buffer.
*   **block_on_recv_queue_full** (default: ``True``):
    *   If ``True``, the background reader pauses when the queue is full (TCP backpressure).
    *   If ``False``, the connection fails with ``OUT_OF_MEMORY`` to prevent silent message loss or massive latency lag.

.. code-block:: python

    # Increase queues for high-throughput streams (e.g., market data)
    ws = await s.ws_connect(
        url,
        recv_queue_size=256,
        send_queue_size=32
    )

Message Limits
--------------

*   **max_message_size** (default: 4MB): The maximum allowed size for a single received message. Messages larger than this will raise a ``WebSocketError`` (Too Large) and close the connection.

.. code-block:: python

    # Allow large payloads (e.g. 16MB)
    ws = await s.ws_connect(url, max_message_size=16 * 1024 * 1024)

There are no limits on the size of the message that can be sent. Messages larger than 64KB are broken into chunks of that size and sent using the ``CONT`` flag which means it arrives as a single logical message on the server.

Frame Coalescing (Throughput)
-----------------------------

For chatty protocols sending many small messages, you can enable **coalescing**. This merges multiple pending messages from the send queue into a single network packet.

*   **coalesce_frames** (default: ``False``): Enable batching.
*   **max_send_batch_size** (default: 32): Max messages to merge.

.. code-block:: python

    # Optimize for throughput over latency
    ws = await s.ws_connect(url, coalesce_frames=True)

Reliability & Retries
---------------------

*   **drain_on_error** (default: ``False``): If ``True``, when a network error occurs, ``recv()`` will continue to yield any buffered messages in the queue before raising the exception. Crucial for ensuring data integrity on unstable connections.
*   **ws_retry**: A policy object to configure automatic retries on failed reads.

.. code-block:: python

    from curl_cffi import WsRetryOnRecvError

    # Retry transient read errors up to 5 times
    retry_policy = WsRetryOnRecvError(
        retry_on_error=True,
        max_retry_count=5
    )

    ws = await s.ws_connect(
        url,
        drain_on_error=True,
        ws_retry=retry_policy
    )

Cooperative Multitasking
------------------------

To prevent the background I/O tasks from starving the asyncio event loop during heavy load, you can tune the time slicing.

*   **recv_time_slice** (default: 0.005s): Max time spent processing incoming packets before yielding.
*   **send_time_slice** (default: 0.001s): Max time spent writing packets before yielding.

.. code-block:: python

    # Force more frequent yields for lower latency in other async tasks
    ws = await s.ws_connect(url, recv_time_slice=0.001)
