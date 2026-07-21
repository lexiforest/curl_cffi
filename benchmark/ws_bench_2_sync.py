#!/usr/bin/env python3
"""
WebSocket benchmark with SHA256 verification (Synchronous Client).
"""

import hashlib
import mmap
import time
from argparse import ArgumentParser, Namespace
from collections.abc import Generator
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

from curl_cffi import Response, Session, WebSocket


async def server_recv_benchmark_handler(ws: web.WebSocketResponse) -> None:
    """Handle the client uploading to this server."""
    logger.info("Connected for upload benchmark (AIOHTTP Server)")
    if not (config.hash_filename.is_file() and config.hash_filename.stat().st_size):
        logger.error("Hash file '%s' not found or empty", config.hash_filename)
        return

    source_hash: str = config.hash_filename.read_text("utf-8").strip()
    logger.info("Loaded hash for '%s': %s", config.data_filename, source_hash)

    try:
        logger.info("Allocating %d GiB memory buffer", config.total_gb)
        with mmap.mmap(-1, config.total_bytes) as testdata_buffer:
            offset: int = 0
            logger.info("Receiving data from client")
            start_time = time.perf_counter()

            async for msg in ws:
                if msg.type is web.WSMsgType.ERROR:
                    logger.error("WebSocket error: %r", ws.exception())
                    return

                if msg.type is web.WSMsgType.BINARY:
                    msg_len: int = len(msg.data)
                    testdata_buffer[offset : offset + msg_len] = msg.data
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

    except Exception:
        logger.exception("Failed to receive data from client")


async def server_send_benchmark_handler(ws: web.WebSocketResponse) -> None:
    """Handle the server sending down to the client."""
    logger.info("Connected for download benchmark (AIOHTTP Server)")
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

        elapsed_time: float = time.perf_counter() - start_time
        logger.info("Sent %d GB in %.2fs", config.total_gb, elapsed_time)
    finally:
        _ = await ws.close()


async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """AIOHTTP server route handler."""
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
        await server_recv_benchmark_handler(ws)
    else:
        await server_send_benchmark_handler(ws)

    return ws


def client_stream_test_data() -> Generator[bytes, None, None]:
    """Synchronously yield test file data in chunks using mmap."""
    drop_interval: int = 512 * 1024 * 1024  # 512 MiB
    file_size: int = config.data_filename.stat().st_size
    logger.info(
        "Streaming '%s' in %d chunks",
        config.data_filename,
        file_size // config.large_chunk_size,
    )

    with (
        config.data_filename.open("rb") as fp,
        mmap.mmap(fp.fileno(), file_size, access=mmap.ACCESS_READ) as mm,
    ):
        can_madvise: bool = hasattr(mm, "madvise")
        if can_madvise:
            mm.madvise(mmap.MADV_SEQUENTIAL, 0, file_size)
        last_drop: int = 0
        start_time: float = time.perf_counter()
        for offset in range(0, file_size, config.large_chunk_size):
            chunk: bytes = mm[offset : offset + config.large_chunk_size]
            yield chunk
            if can_madvise and offset - last_drop >= drop_interval:
                mm.madvise(mmap.MADV_DONTNEED, last_drop, offset - last_drop)
                last_drop = offset

        end_time: float = time.perf_counter()
        if can_madvise and last_drop < file_size:
            mm.madvise(mmap.MADV_DONTNEED, last_drop, file_size - last_drop)

    elapsed_time: float = end_time - start_time
    if elapsed_time > 0:
        disk_speed = (file_size / (1024 * 1024)) / elapsed_time
        logger.info(
            "Streaming '%s' completed in %.2fs. Speed: %.2f MiB/s",
            config.data_filename,
            elapsed_time,
            disk_speed,
        )


def client_recv_benchmark_handler(ws: WebSocket) -> None:
    """Handle the client downloading from the server synchronously."""
    logger.info("Connected for download benchmark (SYNC)")
    if not (config.hash_filename.is_file() and config.hash_filename.stat().st_size):
        logger.error("Hash file '%s' not found or empty", config.hash_filename)
        return

    source_hash: str = config.hash_filename.read_text("utf-8").strip()
    logger.info("Loaded hash for '%s': %s", config.data_filename, source_hash)

    try:
        logger.info("Allocating %d GiB memory buffer", config.total_gb)
        with mmap.mmap(-1, config.total_bytes) as testdata_buffer:
            offset: int = 0
            logger.info("Receiving data from server")
            start_time = time.perf_counter()

            for msg in ws:
                msg_len = len(msg)
                testdata_buffer[offset : offset + msg_len] = msg
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

    except Exception:
        logger.exception("Failed to receive data from server")


def client_send_benchmark_handler(ws: WebSocket) -> None:
    """Handle the client uploading to the server synchronously."""
    logger.info("Connected for upload benchmark (SYNC)")
    try:
        if not (config.data_filename.is_file() and config.data_filename.stat().st_size):
            logger.error(
                "Test data '%s' not found, run 'generate' first.",
                config.data_filename,
            )
            return

        start_time: float = time.perf_counter()
        for chunk in client_stream_test_data():
            _ = ws.send_bytes(chunk)

        elapsed_time: float = time.perf_counter() - start_time
        logger.info("Sent %d GB in %.2fs", config.total_gb, elapsed_time)
    except Exception:
        logger.exception("Failed to send data to server")


def sync_client_handler(opt: str) -> None:
    """Entry logic for the synchronous client."""
    with (
        Session[Response](impersonate="chrome", verify=False) as session,
        session.ws_connect(f"{config.srv_path}?test={opt}") as ws,
    ):
        match opt:
            case "download":
                client_recv_benchmark_handler(ws)
            case "upload":
                client_send_benchmark_handler(ws)
            case _:
                ...


def main() -> None:
    """Entrypoint"""
    mode_opts: list[str] = ["generate", "server", "client"]
    client_opts: list[str] = ["download", "upload"]
    parser: ArgumentParser = ArgumentParser(
        description="WebSocket SHA256 Sync Benchmark"
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
        # Run exclusively with the synchronous curl_cffi client
        sync_client_handler(args.test)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
