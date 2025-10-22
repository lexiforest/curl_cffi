#!/usr/bin/env python3
"""
Websocket client simple benchmark - TLS (WSS)
"""

import time
from asyncio import (
    FIRST_COMPLETED,
    AbstractEventLoop,
    CancelledError,
    Task,
    sleep,
    wait,
)

from typing_extensions import Never
from ws_bench_utils import binary_data_generator, config, get_loop, logger

from curl_cffi import AsyncSession, AsyncWebSocket, WebSocketClosed


def calculate_stats(start_time: float, total_len: int) -> tuple[float, float]:
    """Calculate the amount of time it took and the throughput average.

    Args:
        start_time (`float`): The start time from the performance counter

    Returns:
        `tuple[float, float]`: The duration and rate in Gbps
    """
    end_time: float = time.perf_counter()
    duration: float = end_time - start_time
    rate_gbps: float = (total_len * 8) / duration / (1024**3)
    return duration, rate_gbps


async def health_check() -> Never:
    """A simple coroutine that continuously prints a dot to prove that the event loop
    is alive and not starved from being able to run this task.

    Returns:
        Never: Keeps printing dots until the task is cancelled.
    """
    counter = 0
    logger.info("Starting sanity check. You should see a continuous stream of dots '.'")
    logger.info("If the dots stop for a long time, the event loop is blocked.")
    try:
        while True:
            await sleep(0.05)
            print(".", end="", flush=True)
            counter += 1
            if counter % 100 == 0:
                print("")
    finally:
        print("\r\x1b[K", end="")
        logger.info("Sanity check complete.")


async def ws_counter(ws: AsyncWebSocket) -> None:
    """Simple coroutine which counts how many bytes were received.

    Args:
        ws (`AsyncWebSocket`): Instantiated Curl CFFI AsyncWebSocket object.
    """
    recvd_len: int = 0
    start_time: float = time.perf_counter()
    logger.info("Receiving data from server")
    try:
        async for msg in ws:
            recvd_len += len(msg)

    except WebSocketClosed as exc:
        logger.debug(exc)

    finally:
        duration, avg_rate = calculate_stats(start_time, recvd_len)
        print("\r\x1b[K", end="")
        logger.info(
            "Received: %.2f GB in %.2f seconds", recvd_len / (1024**3), duration
        )
        logger.info("Average throughput (recv): %.2f Gbps", avg_rate)


async def ws_sender(ws: AsyncWebSocket) -> None:
    """Simple coroutine which just sends the same chunk of bytes until exhausted.

    Args:
        ws (`AsyncWebSocket`): Instantiated Curl CFFI AsyncWebSocket object.
    """
    sent_len: int = 0
    start_time: float = time.perf_counter()
    logger.info("Sending data to server")
    try:
        async for data_chunk in binary_data_generator(
            total_gb=config.total_gb, chunk_size=min(65535, config.chunk_size)
        ):
            _ = await ws.send(payload=data_chunk)
            sent_len += len(data_chunk)

    except WebSocketClosed as exc:
        logger.debug(exc)

    finally:
        duration, avg_rate = calculate_stats(start_time, sent_len)
        print("\r\x1b[K", end="")
        logger.info("Sent: %.2f GB in %.2f seconds", sent_len / (1024**3), duration)
        logger.info("Average throughput (send): %.2f Gbps", avg_rate)


async def run_benchmark(loop: AbstractEventLoop) -> None:
    """
    Simple client benchmark which sends/receives binary messages using curl-cffi.
    """
    logger.info("Starting curl-cffi benchmark")
    ws: AsyncWebSocket | None = None
    waiters: set[Task[None]] = set()
    try:
        async with AsyncSession(impersonate="chrome", verify=False) as session:
            ws = await session.ws_connect(config.srv_path)
            logger.info("Connection established to %s", config.srv_path)

            # NOTE: Uncomment for send/recv benchmark or both
            waiters.add(loop.create_task(ws_counter(ws)))
            # waiters.add(loop.create_task(ws_sender(ws)))

            _, _ = await wait(waiters, return_when=FIRST_COMPLETED)

    except Exception:
        logger.exception("curl-cffi benchmark failed")
        raise

    finally:
        for wait_task in waiters:
            try:
                if not wait_task.done():
                    _ = wait_task.cancel()
                    await wait_task

            except CancelledError:
                ...
        if ws:
            await ws.close(timeout=2)


async def main(loop: AbstractEventLoop) -> None:
    """Entrypoint"""
    waiters: set[Task[None]] = set()

    try:
        # Create the health check and benchmark tasks
        waiters.update(
            {loop.create_task(health_check()), loop.create_task(run_benchmark(loop))}
        )
        _, _ = await wait(waiters, return_when=FIRST_COMPLETED)

    except (KeyboardInterrupt, CancelledError):
        logger.debug("Cancelling benchmark")

    finally:
        for wait_task in waiters:
            try:
                if not wait_task.done():
                    _ = wait_task.cancel()
                    await wait_task
            except CancelledError:
                ...


if __name__ == "__main__":
    evt_loop: AbstractEventLoop = get_loop()
    try:
        evt_loop.run_until_complete(main(evt_loop))
    finally:
        evt_loop.close()
