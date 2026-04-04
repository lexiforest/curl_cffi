#!/usr/bin/env python3
"""
WebSocket benchmark with SHA256 verification.
"""

import asyncio
import hashlib
import mmap
import time
from argparse import ArgumentParser, Namespace
from collections.abc import AsyncGenerator
from secrets import compare_digest
from typing import cast

from aiohttp import web
from ws_bench_utils import config, generate_random_chunks, get_loop, logger

from curl_cffi import AsyncSession, AsyncWebSocket, Response


def compare_hash(source_hash: str, received_hash: str) -> None:
    """Compare two hashes and log a message"""
    if compare_digest(source_hash, received_hash):
        logger.info("✅ Hash Verification SUCCESSFUL")
        return

    logger.warning("Received data hash: %s", received_hash)
    logger.warning("❌ Hash Verification FAILED")


def generate_files() -> None:
    """
    Generate the testing data file and its hash, save it to disk.
    """
    logger.info(
        "Generating %d GiB test file: '%s'", config.total_gb, config.data_filename
    )

    if config.data_filename.is_file() and config.data_filename.stat().st_size > 0:
        logger.info("File already exists, skipping generation")
        return

    try:
        # Pre-allocate the disk space
        logger.info("Pre-allocating disk space")
        with config.data_filename.open("wb") as fp:
            _ = fp.seek(config.total_bytes - 1)
            _ = fp.write(b"\0")

        logger.info("Disk space allocation complete")
        hash_object = hashlib.sha256()
        start_time: float = time.perf_counter()

        # Write file to disk
        with (
            config.data_filename.open("r+b") as fpath,
            mmap.mmap(
                fpath.fileno(), config.total_bytes, access=mmap.ACCESS_WRITE
            ) as mm,
        ):
            offset: int = 0
            if hasattr(mm, "madvise"):
                mm.madvise(mmap.MADV_SEQUENTIAL, 0, config.total_bytes)

            logger.info(
                "Writing data in %d chunks",
                config.total_bytes // config.large_chunk_size,
            )
            for chunk in generate_random_chunks():
                hash_object.update(chunk)
                chunk_len = len(chunk)
                mm[offset : offset + chunk_len] = chunk
                offset += chunk_len

            mm.flush()

        end_time: float = time.perf_counter()
        elapsed_time: float = end_time - start_time

        # Write the hashes to file
        final_hash: str = hash_object.hexdigest()
        _ = config.hash_filename.write_text(final_hash, encoding="utf-8")
        logger.info("Hash saved to '%s': %s", config.hash_filename, final_hash)

        if elapsed_time > 0:
            logger.info(
                "Wrote '%s' in %.2fs. Average Speed: %.2f MiB/s",
                config.data_filename,
                elapsed_time,
                (config.total_bytes / (1024 * 1024)) / elapsed_time,
            )

    except Exception:
        logger.exception("Failed to generate file '%s'", config.data_filename)
        return


async def stream_test_data() -> AsyncGenerator[bytes]:
    """Asynchronously yield test file data in chunks using mmap.

    Returns:
        AsyncGenerator[bytes]: Yields chunks of the test file.
    """
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
                mm.madvise(
                    mmap.MADV_DONTNEED,
                    last_drop,
                    offset - last_drop,
                )
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
                        testdata_buffer[offset : offset + msg_len] = msg.data
                        offset += msg_len
            else:
                async for msg in ws:
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
