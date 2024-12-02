import asyncio

from curl_cffi import requests

URL = "ws://echo.websocket.events"


ws = requests.WebSocket().connect(URL)
ws.send(b"Foo")
reply = ws.recv()
print(reply)


async def async_examples():
    async with requests.AsyncSession() as s:
        ws = await s.ws_connect(URL)
        await ws.send(b"Bar")
        reply = await ws.recv()
        print(reply)


asyncio.run(async_examples())
