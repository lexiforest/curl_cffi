#!/usr/bin/env python3
"""
Websocket client simple benchmark - TLS (WSS) - Sync
"""

from threading import Event, Thread
from time import perf_counter, sleep

from ws_bench_utils import (
    BenchmarkDirection,
    binary_data_generator_sync,
    config,
    logger,
)

from curl_cffi import Response, Session, WebSocket, WebSocketClosed


def calculate_stats(start_time: float, total_len: int) -> tuple[float, float]:
    """Calculate the amount of time it took and the throughput average.

    Args:
        start_time (`float`): The start time from the performance counter

    Returns:
        `tuple[float, float]`: The duration and rate in Gbps
    """
    end_time: float = perf_counter()
    duration: float = end_time - start_time
    if duration > 0:
        rate_gbps: float = (total_len * 8) / duration / (1024**3)
    else:
        rate_gbps = 0.0
    return duration, rate_gbps


def health_check(stop_event: Event) -> None:
    """A simple thread that continuously prints a dot to prove that the runtime
    is alive and not starved.
    """
    counter = 0
    logger.info("Starting sanity check. You should see a continuous stream of dots '.'")
    logger.info("If the dots stop for a long time, the thread is blocked.")
    try:
        while not stop_event.is_set():
            sleep(0.05)
            print(".", end="", flush=True)
            counter += 1
            if counter % 100 == 0:
                print("")
    finally:
        print("\r\x1b[K", end="")
        logger.info("Sanity check complete.")


def ws_counter(ws: WebSocket) -> None:
    """Simple method which counts how many bytes were received.

    Args:
        ws (`WebSocket`): Instantiated Curl CFFI WebSocket object.
    """
    recvd_len: int = 0
    expected_bytes: int = config.total_bytes
    start_time: float = perf_counter()
    logger.info("Receiving data from server, expecting %d GiB", config.total_gb)
    try:
        for msg in ws:
            recvd_len += len(msg)
            if recvd_len >= expected_bytes:
                break

    except WebSocketClosed as exc:
        logger.debug(exc)

    finally:
        duration, avg_rate = calculate_stats(start_time, recvd_len)
        print("\r\x1b[K", end="")
        logger.info(
            "Received: %.2f GB in %.2f seconds", recvd_len / (1024**3), duration
        )
        logger.info("Average throughput (recv): %.2f Gbps", avg_rate)


def ws_sender(ws: WebSocket) -> None:
    """Simple method which just sends the same chunk of bytes until exhausted.

    Args:
        ws (`WebSocket`): Instantiated Curl CFFI WebSocket object.
    """
    sent_len: int = 0
    start_time: float = perf_counter()
    logger.info("Sending %dGB of data to server", config.total_gb)
    try:
        for data_chunk in binary_data_generator_sync(
            total_gb=config.total_gb, chunk_size=config.chunk_size
        ):
            _ = ws.send_bytes(data_chunk)
            sent_len += len(data_chunk)

    except WebSocketClosed as exc:
        logger.debug(exc)

    finally:
        duration, avg_rate = calculate_stats(start_time, sent_len)
        print("\r\x1b[K", end="")
        logger.info("Sent: %.2f GB in %.2f seconds", sent_len / (1024**3), duration)
        logger.info("Average throughput (send): %.2f Gbps", avg_rate)


def run_benchmark() -> None:
    """
    Simple client benchmark which sends/receives binary messages using curl-cffi.
    """
    logger.info("Starting curl-cffi WebSocket benchmark (SYNC)")
    try:
        with Session[Response](impersonate="chrome", verify=False) as session:
            logger.info(
                "Client connection established to %s, benchmark direction is %s",
                config.srv_path,
                config.benchmark_direction.name,
            )
            with session.ws_connect(config.srv_path) as ws:
                match config.benchmark_direction:
                    case BenchmarkDirection.READ_ONLY:
                        ws_counter(ws)

                    case BenchmarkDirection.SEND_ONLY:
                        ws_sender(ws)

                    case BenchmarkDirection.CONCURRENT:
                        logger.critical(
                            "Sync WebSocket isn't thread-safe"
                            + " and doesn't support concurrent benchmarks."
                        )

    except Exception:
        logger.exception("curl-cffi benchmark failed")
        raise


def main() -> None:
    """Entrypoint"""
    stop_event: Event = Event()
    health_check_thread: Thread = Thread(
        target=health_check, args=(stop_event,), daemon=True
    )
    health_check_thread.start()

    try:
        run_benchmark()
    except KeyboardInterrupt:
        logger.debug("Cancelling benchmark")
    finally:
        stop_event.set()
        health_check_thread.join()


if __name__ == "__main__":
    main()
