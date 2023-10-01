import asyncio
from curl_cffi import requests
from contextlib import closing

try:
    # Python 3.10+
    from contextlib import aclosing
except ImportError:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def aclosing(thing):
        try:
            yield thing
        finally:
            await thing.aclose()


URL = "https://httpbin.org/stream/20"

with requests.Session() as s:
    print("\n======================================================================")
    print("Iterating over chunks")
    print("=====================================================================\n")
    r = s.get(URL, stream=True)
    for chunk in r.iter_content():
        print("Status: ", r.status_code)
        assert r.status_code == 200
        print("CHUNK", chunk)
    r.close()


    print("\n=====================================================================")
    print("Iterating on a line basis")
    print("=====================================================================\n")
    r = s.get(URL, stream=True)
    for line in r.iter_lines():
        print("Status: ", r.status_code)
        assert r.status_code == 200
        print("LINE", line.decode())
    r.close()


    print("\n=====================================================================")
    print("Better, using closing to ensure the response is closed")
    print("=====================================================================\n")
    with closing(s.get(URL, stream=True)) as r:
        for chunk in r.iter_content():
            print("Status: ", r.status_code)
            assert r.status_code == 200
            print("CHUNK", chunk)


async def async_examples():
    async with requests.AsyncSession() as s:
        print("\n====================================================================")
        print("Using asyncio")
        print("====================================================================\n")
        r = await s.get(URL, stream=True)
        async for chunk in r.aiter_content():
            print("Status: ", r.status_code)
            assert r.status_code == 200
            print("CHUNK", chunk)
        await r.aclose()

        print("\n====================================================================")
        print("Better, using aclosing to ensure the response is closed")
        print("====================================================================\n")
        async with aclosing(await s.get(URL.replace("20", "100"), stream=True)) as r:
            async for chunk in r.aiter_content():
                print("Status: ", r.status_code)
                assert r.status_code == 200
                print("CHUNK", chunk)


asyncio.run(async_examples())
