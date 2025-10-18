#!/usr/bin/env python3
"""
Websocket server example - TLS (WSS)
"""

import os
from asyncio import (
    FIRST_COMPLETED,
    AbstractEventLoop,
    CancelledError,
    Task,
    get_running_loop,
    set_event_loop,
    wait,
)
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from ipaddress import IPv4Address
from logging import DEBUG, Formatter, Logger, StreamHandler, getLogger
from pathlib import Path
from ssl import PROTOCOL_TLS_SERVER, SSLContext
from typing import TextIO

import uvloop
from aiohttp import web


@dataclass
class TestConfig:
    """
    Configuration values, should be changed as needed.
    """

    total_gb: int = 10
    chunk_size: int = 65536
    cert_file: Path = Path("localhost.crt")
    cert_key: Path = Path("localhost.key")
    data_filename: Path = Path("testdata.bin")
    hash_filename: Path = data_filename.with_suffix(".hash")
    srv_host: IPv4Address = IPv4Address("127.0.0.1")
    srv_port: int = 4443


def get_logger() -> Logger:
    """Setup the logger.

    Returns:
        Logger: Initialized logger object
    """
    console: Logger = getLogger(name=__name__)
    console_handler: StreamHandler[TextIO] = StreamHandler()
    console.setLevel(level=DEBUG)
    console_handler.setLevel(level=DEBUG)
    formatter: Formatter = Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s", datefmt="%d-%m-%Y %H:%M:%S"
    )
    console_handler.setFormatter(fmt=formatter)
    console.addHandler(hdlr=console_handler)
    return console


# Initialize instances
logger: Logger = get_logger()
config: TestConfig = TestConfig()


async def binary_data_generator(
    total_gb: float, chunk_size: int
) -> AsyncGenerator[bytes]:
    """An asynchronous generator that yields chunks of binary data efficiently
    for benchmarking. It generates one chunk of random data and reuses it to
    eliminate chunk generation overhead as a performance factor.

    Args:
        total_gb (`float`): The total amount of data to generate.
        chunk_size (`int`): Data should be yielded in chunks of this size.

    Yields:
        `Iterator[AsyncGenerator[bytes, None]]`: Chunks until total size is reached.
    """
    bytes_to_send: int = int(total_gb * 1024**3)
    bytes_sent = 0

    # Create one reusable chunk of random data to avoid calling os.urandom() in a loop.
    reusable_chunk = os.urandom(chunk_size)
    while bytes_sent < bytes_to_send:
        # Calculate the size of the next chunk to send
        current_chunk_size = min(chunk_size, bytes_to_send - bytes_sent)

        # If it's a full-sized chunk, yield the reusable one. Otherwise, yield a slice.
        if current_chunk_size == chunk_size:
            yield reusable_chunk
        else:
            yield reusable_chunk[:current_chunk_size]
        bytes_sent += current_chunk_size


async def recv(ws: web.WebSocketResponse) -> None:
    """Just receive the data in a tight loop. Do nothing else.

    Args:
        ws (web.WebSocketResponse): The WebSocket server object.
    """
    async for msg in ws:
        if msg.type == web.WSMsgType.BINARY:
            continue

        if msg.type == web.WSMsgType.ERROR:
            break


async def send(ws: web.WebSocketResponse) -> None:
    """Send the generated chunks until total size is hit.

    Args:
        ws (web.WebSocketResponse): The WebSocket server object.
    """
    try:
        async for binary_data in binary_data_generator(
            config.total_gb, config.chunk_size
        ):
            await ws.send_bytes(binary_data)
    except ConnectionError as exc:
        logger.warning(exc)


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle the connection and run the relevant server action, send/recv/both.

    Args:
        request (web.Request): Web request object.

    Returns:
        web.WebSocketResponse: Response object
    """
    loop: AbstractEventLoop = get_running_loop()
    waiters: set[Task[None]] = set()
    ws: web.WebSocketResponse = web.WebSocketResponse()
    _ = await ws.prepare(request)
    logger.info("Secure client connected.")

    try:
        # Uncomment for send/recv or both concurrently
        # waiters.add(loop.create_task(recv(ws)))
        waiters.add(loop.create_task(send(ws)))

        _, _ = await wait(waiters, return_when=FIRST_COMPLETED)

    except Exception:
        logger.exception("Connection closed with exception")

    finally:
        for wait_task in waiters:
            try:
                if not wait_task.done():
                    _ = wait_task.cancel()
                    await wait_task
            except CancelledError:
                ...

    logger.info("Client disconnected.")
    return ws


def main() -> None:
    """Entrypoint"""

    # Uvloop specific
    loop: AbstractEventLoop = uvloop.new_event_loop()
    set_event_loop(loop)

    # Comment this and related bits out if you don't want WSS/TLS
    if not (config.cert_file.is_file() and config.cert_key.is_file()):
        logger.error(
            "Certificate file(s) %s or %s not found, please see README.md",
            config.cert_file,
            config.cert_key,
        )
        return
    ssl_context: SSLContext = SSLContext(PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(config.cert_file, config.cert_key)

    # Create and start the aiohttp server
    app: web.Application = web.Application()
    _ = app.add_routes(routes=[web.get("/ws", ws_handler)])
    logger.info("Starting server on wss://%s:%d/ws", config.srv_host, config.srv_port)
    web.run_app(
        app,
        host=config.srv_host.exploded,
        port=config.srv_port,
        loop=loop,
        ssl_context=ssl_context,
        access_log=logger,
        print=logger.debug,
    )


if __name__ == "__main__":
    main()
