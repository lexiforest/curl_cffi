import asyncio

from curl_cffi import requests

URL = "ws://echo.websocket.events"

with requests.Session() as s:
    w = s.ws_connect(URL)
    w.send(b"Foo")
    reply = w.recv()
    print(reply)


async def async_examples():
    async with requests.AsyncSession() as s:
        w = await s.ws_connect(URL)
        await w.asend(b"Bar")
        reply = await w.arecv()
        print(reply)


asyncio.run(async_examples())
