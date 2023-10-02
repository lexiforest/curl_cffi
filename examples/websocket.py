import asyncio
from curl_cffi import requests

with requests.Session() as s:
    w = s.connect("ws://localhost:8765")
    w.send(b"Foo")
    reply = w.recv()
    print(reply)
    assert reply == b"Hello Foo!"


async def async_examples():
    async with requests.AsyncSession() as s:
        w = await s.connect("ws://localhost:8765")
        await w.asend(b"Bar")
        reply = await w.arecv()
        print(reply)
        assert reply == b"Hello Bar!"


asyncio.run(async_examples())
