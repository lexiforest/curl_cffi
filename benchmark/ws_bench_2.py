#!/usr/bin/env python3
"""
WebSocket benchmark with SHA256 verification.
"""
import asyncio
import hashlib
import mmap
import os

# import ssl
import sys
import time
from argparse import ArgumentParser, Namespace
from collections.abc import AsyncGenerator

# from ssl import SSLContext
from typing import cast

import uvloop

# from aiohttp import web
from ws_bench_1_server import config, logger

# from curl_cffi import AsyncSession, CurlOpt

# Config
TOTAL_BYTES: int = int(config.total_gb * 1024**3)
CHUNK_SIZE: int = 4 * 1024 * 1024  # 4MiB


async def generate_random_chunks() -> AsyncGenerator[bytes]:
    """Generate chunks of random data.

    Returns:
        AsyncGenerator[bytes]: Async generator that yields random chunks.
    """
    num_chunks: int = TOTAL_BYTES // CHUNK_SIZE
    for _ in range(num_chunks):
        yield os.urandom(CHUNK_SIZE)
        await asyncio.sleep(0)

    remaining_size = TOTAL_BYTES % CHUNK_SIZE
    if remaining_size > 0:
        yield os.urandom(remaining_size)


async def generate_files() -> None:
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
            can_madvise = hasattr(mm, "madvise")
            if can_madvise:
                mm.madvise(mmap.MADV_SEQUENTIAL)

            logger.info("Writing data in %d chunks", TOTAL_BYTES // CHUNK_SIZE)
            async for chunk in generate_random_chunks():
                hash_object.update(chunk)
                chunk_len = len(chunk)
                mm[offset : offset + chunk_len] = chunk
                offset += chunk_len

            mm.flush()

        end_time: float = time.perf_counter()
        elapsed_time: float = end_time - start_time

        # Write the hashes to file
        final_hash: str = hash_object.hexdigest()
        _ = config.hash_filename.write_text(final_hash)
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


async def main() -> None:
    """Entrypoint"""
    parser: ArgumentParser = ArgumentParser(
        description="WebSocket Unidirectional Benchmark"
    )
    _ = parser.add_argument(
        "mode", choices=["generate", "server", "client"], help="Operation", type=str
    )
    _ = parser.add_argument(
        "--test", choices=["download", "upload"], default="download", type=str
    )
    args: Namespace = parser.parse_args()
    args.mode = cast(str, args.mode)
    args.test = cast(str, args.test)

    if args.mode == "generate":
        await generate_files()

    elif args.mode == "server":
        ...
        # await start_server()

    # elif args.mode == "client":
    #     if args.test == "download":
    #         ...
    #         source_hash = load_source_hash()
    #         await download_client(source_hash)

    #     elif args.test == "upload":
    #         ...
    #         await upload_client()

    else:
        parser.print_help()


if __name__ == "__main__":
    if sys.platform != "win32":
        uvloop.run(main())
    else:
        asyncio.run(main())
