import asyncio

import curl_cffi


async def main():
    async with curl_cffi.AsyncSession() as s:
        ws = await s.ws_connect("wss://api.gemini.com/v1/marketdata/BTCUSD")
        print(
            "For websockets, you need to set $wss_proxy environment variable!\n"
            "$https_proxy will not work!"
        )
        print(">>> Websocket open!")

        async for message in ws:
            print(message)

        print("<<< Websocket closed!")


asyncio.run(main())
