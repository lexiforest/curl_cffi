Async WebSockets
****************

``curl_cffi`` provides a high-performance, asyncio-compatible WebSocket client powered by libcurl.
It supports standard WebSocket features like text/binary frames, pings, and automatic handling of control frames.

The implementation uses a decoupled I/O model: sending puts messages into a queue (non-blocking), and receiving waits on a queue populated by a background task.

Quick Start
===========

The recommended way to use WebSockets is via the `AsyncSession` context manager.

.. code-block:: python

    import asyncio
    from curl_cffi import AsyncSession

    async def main():
        async with AsyncSession() as s:
            async with await s.ws_connect("wss://echo.websocket.org") as ws:
                # Send a text message
                await ws.send_str("Hello, World!")

                # Receive a text message
                msg = await ws.recv_str()
                print(f"Received: {msg}")

    asyncio.run(main())

Connecting
==========

Use ``ws_connect`` from an ``AsyncSession``. This method accepts the same connection parameters as ``request`` (headers, auth, proxies, impersonate, etc.).

.. code-block:: python

    async with AsyncSession() as s:
        async with await s.ws_connect(
            "wss://api.example.com/v1/stream",
            impersonate="chrome",
            auth=("user", "pass")
        ) as ws:
            ...

You must ``await`` the connection first to get the ``ws`` object, then use that object in the context manager, e.g. ``async with await s.ws_connect(...)``.

Sending Data
============

There are helper methods for different data types.

Sending Text
------------

.. code-block:: python

    await ws.send_str("Hello")

Sending Bytes
-------------

.. code-block:: python

    await ws.send_bytes(b"\x00\x01\x02")

Sending JSON
------------

Automatically serializes a dictionary to a JSON string.

.. code-block:: python

    await ws.send_json({"action": "subscribe", "channel": "btc_usd"})


Sending Pings
-------------

Libcurl handles Pongs automatically, but you can send a manual Ping frame if needed.

.. code-block:: python

    await ws.ping(b"keepalive")


Receiving Data
==============

You can receive individual messages or iterate over the connection.

Receive Methods
---------------

.. code-block:: python

    # Receive as string
    msg = await ws.recv_str()

    # Receive and parse JSON
    data = await ws.recv_json()

    # Receive raw bytes and frame flags
    # This is useful if you need to inspect frame flags (e.g., CONTINUATION)
    content, flags = await ws.recv()


Async Iteration
---------------

You can iterate over the WebSocket object.

.. note::

    Iteration yields ``bytes``. If you expect text, you must decode it yourself.

.. code-block:: python

    async for chunk in ws:
        print(chunk.decode("utf-8"))


Error Handling
==============

Common exceptions include ``WebSocketClosed`` (connection closed normally or abnormally) and ``WebSocketTimeout``.

.. code-block:: python

    from curl_cffi import WebSocketClosed, WebSocketTimeout

    try:
        msg = await ws.recv_str()
    except WebSocketClosed as e:
        print(f"Closed: {e.code} - {e.message}")
    except WebSocketTimeout:
        print("Did not receive a message in time.")


Performance & Configuration
===========================

The ``AsyncWebSocket`` implementation is tuned for high concurrency. You can adjust queue sizes and batching behavior in ``ws_connect``.

Queue Sizes (Backpressure)
--------------------------

*   **recv_queue_size** (default: 128): Max number of incoming messages to buffer.
*   **send_queue_size** (default: 16): Max number of outgoing messages to buffer.

If the send queue is full, ``await ws.send()`` will block until space is available, creating natural backpressure.

.. code-block:: python

    # Increase queues for high-throughput streams
    ws = await s.ws_connect(
        url,
        recv_queue_size=1024,
        send_queue_size=1024
    )

Frame Coalescing
----------------

For chatty protocols sending many small messages, you can enable **coalescing**. This merges multiple pending messages from the send queue into a single TCP packet/WebSocket frame sequence, significantly increasing throughput at the cost of slightly higher latency.

.. code-block:: python

    # Enable for high-throughput uploads
    ws = await s.ws_connect(url, coalesce_frames=True)


Flushing
--------

Since ``send()`` puts messages into a background queue, use ``flush()`` to ensure all queued messages have been written to the socket.

.. code-block:: python

    await ws.send_str("Important Data")
    await ws.flush()  # Wait until data leaves the client


Drain on Error
--------------

By default, if the connection drops, ``recv()`` raises an exception immediately.
If you set ``drain_on_error=True``, ``recv()`` will continue to yield any buffered messages in the memory queue before raising the connection error.

.. code-block:: python

    # Ensure we process every last message even if the net cuts out
    ws = await s.ws_connect(url, drain_on_error=True)
