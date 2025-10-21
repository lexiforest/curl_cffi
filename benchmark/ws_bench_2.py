#!/usr/bin/env python3
"""
WebSocket benchmark with SHA256 verification.
"""
import asyncio
import hashlib
import mmap
import os
import time
from argparse import ArgumentParser, Namespace
from collections.abc import AsyncGenerator, Generator
from secrets import compare_digest
from ssl import PROTOCOL_TLS_SERVER, SSLContext
from typing import cast

from aiohttp import web
from aiohttp.helpers import IS_WINDOWS

from curl_cffi import AsyncSession, AsyncWebSocket

from ws_bench_1_server import config, logger


# Config
TOTAL_BYTES: int = int(config.total_gb * 1024**3)
CHUNK_SIZE: int = 4 * 1024 * 1024  # 4MiB


def compare_hash(source_hash: str, received_hash: str) -> None:
    """Compare two hashes and log a message"""
    if compare_digest(source_hash, received_hash):
        logger.info("✅ Server-Side Hash Verification SUCCESSFUL")
        return

    logger.warning("Received data hash: %s", received_hash)
    logger.warning("❌ Server-Side Hash Verification FAILED")


def generate_random_chunks() -> Generator[bytes]:
    """Generate chunks of random data up to a total size.

    Returns:
        Generator[bytes]: Generator that yields random chunks.
    """
    num_chunks: int = TOTAL_BYTES // CHUNK_SIZE
    for _ in range(num_chunks):
        yield os.urandom(CHUNK_SIZE)

    remaining_size = TOTAL_BYTES % CHUNK_SIZE
    if remaining_size > 0:
        yield os.urandom(remaining_size)


def get_ssl_ctx() -> SSLContext | None:
    """Load in the SSL context if cert files present and host is non-Windows.

    Returns:
        `SSLContext | None`: The SSL context or `None`.
    """
    if IS_WINDOWS:
        logger.info("Disabling TLS due to Windows host")
        return None

    if not (config.cert_file.is_file() and config.cert_key.is_file()):
        logger.warning(
            "Certificate file(s) %s or %s not found, disabling TLS",
            config.cert_file,
            config.cert_key,
        )
        return None

    ssl_context: SSLContext = SSLContext(PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(config.cert_file, config.cert_key)
    return ssl_context


def get_loop() -> asyncio.AbstractEventLoop:
    """Returns the correct event loop for the platform and what's installed.

    Returns:
        asyncio.AbstractEventLoop: The created and installed event loop.
    """

    try:
        # pylint: disable-next=import-outside-toplevel
        import uvloop

        loop: asyncio.AbstractEventLoop = uvloop.new_event_loop()
    except ImportError:
        loop = asyncio.new_event_loop()

    asyncio.set_event_loop(loop)
    return loop


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
            _ = fp.seek(TOTAL_BYTES - 1)
            _ = fp.write(b"\0")

        logger.info("Disk space allocation complete")
        hash_object = hashlib.sha256()
        start_time: float = time.perf_counter()

        # Write file to disk
        with (
            config.data_filename.open("r+b") as fpath,
            mmap.mmap(fpath.fileno(), TOTAL_BYTES, access=mmap.ACCESS_WRITE) as mm,
        ):
            offset: int = 0
            if hasattr(mm, "madvise"):
                mm.madvise(mmap.MADV_SEQUENTIAL, 0, TOTAL_BYTES)

            logger.info("Writing data in %d chunks", TOTAL_BYTES // CHUNK_SIZE)
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
                (TOTAL_BYTES / (1024 * 1024)) / elapsed_time,
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
        "Streaming '%s' in %d chunks", config.data_filename, file_size // CHUNK_SIZE
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
        for offset in range(0, file_size, CHUNK_SIZE):
            chunk: bytes = mm[offset : offset + CHUNK_SIZE]
            yield chunk
            await asyncio.sleep(0)
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

    # Allocate data buffer ahead of time
    logger.info("Allocating memory buffer of %d GB", config.total_gb)
    testdata_buffer: bytearray = bytearray()
    try:
        start_time: float = time.perf_counter()
        testdata_buffer = bytearray(TOTAL_BYTES)
        elapsed_time: float = time.perf_counter() - start_time
        logger.info(
            "Allocated %d GB in %.2fs. Speed: %.2f MiB/s ",
            config.total_gb,
            elapsed_time,
            (TOTAL_BYTES / (1024**2)) / elapsed_time,
        )
    except MemoryError:
        logger.exception("Not enough RAM to allocate %d GB", config.total_gb)
        return

    try:
        # Receive the data into the buffer
        offset: int = 0
        logger.info("Receiving data from client")
        start_time = time.perf_counter()
        if isinstance(ws, web.WebSocketResponse):
            logger.info("WebSocket connection type: SERVER")
            async for msg in ws:
                if msg.type == web.WSMsgType.BINARY:
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
    except Exception:
        logger.exception("Failed to receive data from client")

    del testdata_buffer


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

        if isinstance(ws, AsyncWebSocket):
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
    ws: web.WebSocketResponse = web.WebSocketResponse()
    _ = await ws.prepare(request)
    logger.info("Client connected %s", request.host)

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
    async with AsyncSession(impersonate="chrome", verify=False) as session:
        ws: AsyncWebSocket = await session.ws_connect(
            f"wss://127.0.0.1:4443/ws?test={opt}"
        )
        try:
            if opt == "download":
                await recv_benchmark_handler(ws)
                return

            await send_benchmark_handler(ws)

        finally:
            await ws.close()


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
        logger.info(
            "Starting server on wss://%s:%d/ws", config.srv_host, config.srv_port
        )
        web.run_app(
            app,
            host=config.srv_host.exploded,
            port=config.srv_port,
            loop=get_loop(),
            ssl_context=get_ssl_ctx(),
            access_log=logger,
            print=logger.debug,
        )

    elif args.mode == "client" and args.test in client_opts:
        loop: asyncio.AbstractEventLoop = get_loop()
        loop.run_until_complete(client_handler(args.test))
        loop.close()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
