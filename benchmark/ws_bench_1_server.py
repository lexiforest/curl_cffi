#!/usr/bin/env python3
"""
Websocket server example - TLS (WSS)
"""

from asyncio import (
    FIRST_COMPLETED,
    AbstractEventLoop,
    CancelledError,
    Task,
    get_running_loop,
    wait,
)

from aiohttp import web
from ws_bench_utils import (
    BenchmarkDirection,
    binary_data_generator,
    config,
    get_loop,
    logger,
)


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
    waiters: set[Task[None]] = set[Task[None]]()
    ws: web.WebSocketResponse = web.WebSocketResponse()
    _ = await ws.prepare(request)
    logger.info("Secure client connected.")

    try:
        # This is server side so everything is reversed
        match config.benchmark_direction:
            case BenchmarkDirection.READ_ONLY:
                waiters.add(loop.create_task(send(ws)))

            case BenchmarkDirection.SEND_ONLY:
                waiters.add(loop.create_task(recv(ws)))

            case BenchmarkDirection.CONCURRENT:
                waiters.add(loop.create_task(send(ws)))
                waiters.add(loop.create_task(recv(ws)))

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

    # Create and start the aiohttp server
    app: web.Application = web.Application()
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


if __name__ == "__main__":
    main()
