#!/usr/bin/env python3
"""
Cross-platform utility code for the WebSocket benchmarks.
"""

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass
from enum import Enum, auto
from ipaddress import IPv4Address
from logging import DEBUG, Formatter, Logger, StreamHandler, getLogger
from pathlib import Path
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
    recv_queue: int = 32
    send_queue: int = 16
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
