"""
WIP: this has not been implemented yet.
"""

import asyncio

from curl_cffi import requests


async def on_message(ws, message):
    print(message)


async def on_error(ws, error):
    print(error)


async def on_open(ws):
    print(
        "For websockets, you need to set $wss_proxy environment variable!\n"
        "$https_proxy will not work!"
    )
    print(">>> Websocket open!")


async def on_close(ws):
    print("<<< Websocket closed!")


async def main():
    async with requests.AsyncSession() as s:
        ws = await s.ws_connect(
            "wss://api.gemini.com/v1/marketdata/BTCUSD",
            on_open=on_open,
            on_close=on_close,
            on_message=on_message,
            on_error=on_error,
        )
        ws.run_forever()


asyncio.run(main())
