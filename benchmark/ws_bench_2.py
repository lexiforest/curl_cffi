#!/usr/bin/env python3
"""
WebSocket benchmark with SHA256 verification.
"""

import asyncio
import hashlib
import mmap
import time
from argparse import ArgumentParser, Namespace
from typing import cast

from aiohttp import web
from ws_bench_utils import (
    compare_hash,
    config,
    generate_files,
    get_loop,
    logger,
    stream_test_data,
)

from curl_cffi import AsyncSession, AsyncWebSocket, Response


async def recv_benchmark_handler(ws: web.WebSocketResponse | AsyncWebSocket) -> None:
    """Handle the download benchmark, either as server or a client.

    Args:
        ws (web.WebSocketResponse | AsyncWebSocket): AIOHTTP or Curl-CFFI WebSocket.
    """
    logger.info("Connected for download benchmark")
    if not (config.hash_filename.is_file() and config.hash_filename.stat().st_size):
        logger.error("Hash file '%s' not found or empty", config.hash_filename)
        return

    source_hash: str = config.hash_filename.read_text("utf-8").strip()
    logger.info("Loaded hash for '%s': %s", config.data_filename, source_hash)

    try:
        logger.info("Allocating %d GiB memory buffer", config.total_gb)
        with mmap.mmap(-1, config.total_bytes) as testdata_buffer:
            # Receive the data into the buffer
            offset: int = 0
            logger.info("Receiving data from client")
            start_time = time.perf_counter()
            if isinstance(ws, web.WebSocketResponse):
                logger.info("WebSocket type: SERVER")
                async for msg in ws:
                    if msg.type is web.WSMsgType.ERROR:
                        logger.error("WebSocket error: %r", ws.exception())
                        return

                    if msg.type is web.WSMsgType.BINARY:
                        msg_len: int = len(msg.data)
                        testdata_buffer[offset: offset + msg_len] = msg.data
                        offset += msg_len
            else:
                async for msg in ws:
                    msg_len = len(msg)
                    testdata_buffer[offset: offset + msg_len] = msg
                    offset += msg_len

            elapsed_time = time.perf_counter() - start_time
            logger.info(
                "Received %.2f GB in %.2fs. Speed: %.2f MiB/s ",
                offset / (1024**3),
                elapsed_time,
                (offset / (1024**2)) / elapsed_time,
            )

            if offset < config.total_bytes - config.chunk_size:
                logger.error("Incomplete file received, skipping hash check")
                return

            # Calculate and compare hashes
            logger.info("Calculating hash of received data")
            start_time = time.perf_counter()
            received_hash = hashlib.sha256(testdata_buffer).hexdigest()
            elapsed_time = time.perf_counter() - start_time
            logger.info(
                "Hash calculated in %.2fs. Speed: %.2f MiB/s ",
                elapsed_time,
                (offset / (1024**2)) / elapsed_time,
            )
            compare_hash(source_hash, received_hash)

    # pylint: disable-next=broad-exception-caught
    except Exception:
        logger.exception("Failed to receive data from client")


async def send_benchmark_handler(ws: web.WebSocketResponse | AsyncWebSocket) -> None:
    """Handle the upload benchmark either as a server or client.

    Args:
        ws (web.WebSocketResponse | AsyncWebSocket): AIOHTTP or Curl-CFFI WebSocket.
    """
    logger.info("Connected for upload benchmark")
    try:
        if not (config.data_filename.is_file() and config.data_filename.stat().st_size):
            logger.error(
                "Test data '%s' not found, run 'generate' first.",
                config.data_filename,
            )
            return

        start_time: float = time.perf_counter()
        async for chunk in stream_test_data():
            await ws.send_bytes(chunk)

        # Wait for all the data to be sent
        if isinstance(ws, AsyncWebSocket):
            logger.info("Waiting for send queue to be flushed")
            await ws.flush()

        elapsed_time: float = time.perf_counter() - start_time
        logger.info("Sent %d GB in %.2fs", config.total_gb, elapsed_time)
    finally:
        if isinstance(ws, web.WebSocketResponse):
            _ = await ws.close()


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle the request and run the relevant server action.

    Args:
        request (web.Request): HTTP request object.

    Returns:
        web.WebSocketResponse: Response object.
    """
    ws: web.WebSocketResponse = web.WebSocketResponse(
        max_msg_size=config.server_max_msg
    )
    _ = await ws.prepare(request)
    logger.info(
        "Client connected from %s, max message size is %d",
        request.host,
        config.server_max_msg,
    )

    if request.query.get("test") == "upload":
        await recv_benchmark_handler(ws)
    else:
        await send_benchmark_handler(ws)

    return ws


async def client_handler(opt: str) -> None:
    """Handle the client benchmark functions.

    Args:
        opt (str): The benchmark mode to run.
    """
    async with (
        AsyncSession[Response](impersonate="chrome", verify=False) as session,
        session.ws_connect(
            f"{config.srv_path}?test={opt}",
            recv_queue_size=config.recv_queue,
            send_queue_size=config.send_queue,
        ) as ws,
    ):
        match opt:
            case "download":
                await recv_benchmark_handler(ws)

            case "upload":
                await send_benchmark_handler(ws)

            case _:
                ...


def main() -> None:
    """Entrypoint"""
    mode_opts: list[str] = ["generate", "server", "client"]
    client_opts: list[str] = ["download", "upload"]
    parser: ArgumentParser = ArgumentParser(
        description="WebSocket Unidirectional Benchmark"
    )
    _ = parser.add_argument("mode", choices=mode_opts, help="Operation", type=str)
    _ = parser.add_argument(
        "-t", "--test", choices=client_opts, default="download", type=str
    )
    args: Namespace = parser.parse_args()
    args.mode = cast(str, args.mode)
    args.test = cast(str, args.test)

    if args.mode == "generate":
        generate_files()

    elif args.mode == "server":
        app: web.Application = web.Application(logger=logger)
        _ = app.add_routes(routes=[web.get("/ws", ws_handler)])
        logger.info("Starting server on %s", config.srv_path)
        web.run_app(
            app,
            host=config.srv_host.exploded,
            port=config.srv_port,
            loop=get_loop(),
            ssl_context=config.ssl_ctx,
            access_log=logger,
            print=logger.debug,
        )

    elif args.mode == "client" and args.test in client_opts:
        try:
            # pylint: disable-next=import-outside-toplevel
            import uvloop

            uvloop.run(client_handler(args.test))
        except ImportError:
            asyncio.run(client_handler(args.test))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
