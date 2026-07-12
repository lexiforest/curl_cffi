#!/usr/bin/env python3
"""
Cross-platform utility code for the WebSocket benchmarks.
"""

import asyncio
import hashlib
import mmap
import os
import time
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from enum import Enum, auto
from ipaddress import IPv4Address
from logging import DEBUG, Formatter, Logger, StreamHandler, getLogger
from pathlib import Path
from secrets import compare_digest
from ssl import PROTOCOL_TLS_SERVER, SSLContext
from typing import TextIO


class BenchmarkDirection(Enum):
    """Enum which controls the direction of the benchmarks.
    Read benchmarks only test the download performance (default).
    Send benchmarks only test uploads and concurrent will run
    the send and receive benchmarks at the same time.

    Args:
        Enum (int): The benchmark direction to use.
    """

    READ_ONLY = auto()
    SEND_ONLY = auto()
    CONCURRENT = auto()


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


# Initialize logger
logger: Logger = get_logger()


def get_ssl_ctx(cert_file: Path, cert_key: Path) -> SSLContext | None:
    """Load in the SSL context if cert files present and host is non-Windows.

    Returns:
        `SSLContext | None`: The SSL context or `None`.
    """

    if not (cert_file.is_file() and cert_key.is_file()):
        logger.warning(
            "Certificate file(s) %s or %s not found, disabling TLS",
            cert_file,
            cert_key,
        )
        return None

    ssl_context: SSLContext = SSLContext(PROTOCOL_TLS_SERVER)
    ssl_context.load_cert_chain(cert_file, cert_key)
    return ssl_context


@dataclass
class TestConfig:
    """
    Configuration values, should be changed as needed.

    NOTE: On Linux madvise requires alignment of free chunks,
    so ``large_chunk_size`` must be a page-aligned value.
    """

    total_gb: int = 10
    chunk_size: int = 65536
    large_chunk_size: int = 4 * 1024**2
    server_max_msg: int = 8 * 1024**2
    total_bytes: int = total_gb * 1024**3
    recv_queue: int = 64
    send_queue: int = 32
    cert_file: Path = Path("localhost.crt")
    cert_key: Path = Path("localhost.key")
    data_filename: Path = Path("testdata.bin")
    hash_filename: Path = data_filename.with_suffix(".hash")
    srv_host: IPv4Address = IPv4Address("127.0.0.1")
    srv_port: int = 4443
    ssl_ctx: SSLContext | None = get_ssl_ctx(cert_file, cert_key)
    proto: str = "wss://" if ssl_ctx else "ws://"
    srv_path: str = f"{proto}{srv_host}:{srv_port}/ws"
    benchmark_direction: BenchmarkDirection = BenchmarkDirection.READ_ONLY


# Initialize config object
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
    reusable_chunk: bytes = os.urandom(chunk_size)
    while bytes_sent < bytes_to_send:
        # Calculate the size of the next chunk to send
        current_chunk_size: int = min(chunk_size, bytes_to_send - bytes_sent)

        # If it's a full-sized chunk, yield the reusable one. Otherwise, yield a slice.
        if current_chunk_size == chunk_size:
            yield reusable_chunk
        else:
            yield reusable_chunk[:current_chunk_size]
        bytes_sent += current_chunk_size


def binary_data_generator_sync(
    total_gb: float, chunk_size: int
) -> Generator[bytes, None, None]:
    """A synchronous generator that yields chunks of binary data efficiently.

    Args:
        total_gb (`float`): The total amount of data to generate.
        chunk_size (`int`): Data should be yielded in chunks of this size.

    Yields:
        `Generator[bytes, None, None]`: Chunks until total size is reached.
    """
    bytes_to_send: int = int(total_gb * 1024**3)
    bytes_sent = 0

    reusable_chunk: bytes = os.urandom(chunk_size)
    while bytes_sent < bytes_to_send:
        current_chunk_size: int = min(chunk_size, bytes_to_send - bytes_sent)

        if current_chunk_size == chunk_size:
            yield reusable_chunk
        else:
            yield reusable_chunk[:current_chunk_size]
        bytes_sent += current_chunk_size


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


def generate_random_chunks() -> Generator[bytes]:
    """Generate chunks of random data up to a total size.

    Returns:
        Generator[bytes]: Generator that yields random chunks.
    """
    num_chunks: int = config.total_bytes // config.large_chunk_size
    for _ in range(num_chunks):
        yield os.urandom(config.large_chunk_size)

    remaining_size: int = config.total_bytes % config.large_chunk_size
    if remaining_size > 0:
        yield os.urandom(remaining_size)


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
