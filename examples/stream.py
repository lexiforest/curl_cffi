import asyncio
from contextlib import closing

from curl_cffi import requests

try:
    # Python 3.10+
    from contextlib import aclosing  # pyright: ignore
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

    print("\n====================================================================")
    print("Empty body is fine.")
    print("====================================================================\n")
    response = s.get("https://httpbin.org/status/202", stream=True)
    print(response.status_code)
    response.close()

    print("\n====================================================================")
    print("Using with stream")
    print("====================================================================\n")
    with s.stream("GET", URL) as r:
        print("Status: ", r.status_code)
        for chunk in r.iter_content():
            assert r.status_code == 200
            print("CHUNK", chunk)

    print("\n=====================================================================")
    print("Iterating on a line basis")
    print("=====================================================================\n")
    r = s.get(URL, stream=True)
    print("Status: ", r.status_code)
    for line in r.iter_lines():
        assert r.status_code == 200
        print("LINE", line.decode())
    r.close()

    print("\n======================================================================")
    print("Break when reading")
    print("=====================================================================\n")
    r = s.get("https://httpbin.org/drip", stream=True)
    for idx, chunk in enumerate(r.iter_content()):
        print(f"{idx}={chunk.decode()}", end="#", flush=True)
        if idx == 3:
            break
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
        print("Empty body is fine.")
        print("====================================================================\n")
        response = await s.get("https://httpbin.org/status/202", stream=True)
        print(response.status_code)
        await response.aclose()

        print("\n====================================================================")
        print("Using asyncio async with stream")
        print("====================================================================\n")
        async with s.stream("GET", URL) as r:
            async for chunk in r.aiter_content():
                print("Status: ", r.status_code)
                assert r.status_code == 200
                print("CHUNK", chunk)

        print("\n======================================================================")
        print("Break when reading")
        print("=====================================================================\n")
        async with s.stream("GET", "https://httpbin.org/drip") as r:
            idx = 0
            async for chunk in r.aiter_content():
                idx += 1
                print(f"{idx}={chunk.decode()}", end="#", flush=True)
                if idx == 3:
                    break

        print("\n====================================================================")
        print("Stream, but not stream, await atext")
        print("====================================================================\n")
        async with s.stream("GET", URL) as r:
            print(await r.atext())

        print("\n====================================================================")
        print("Using asyncio async with stream")
        print("====================================================================\n")
        async with s.stream("GET", URL) as r:
            async for chunk in r.aiter_content():
                print("Status: ", r.status_code)
                assert r.status_code == 200
                print("CHUNK", chunk)

        print("\n====================================================================")
        print("Better, using aclosing to ensure the response is closed")
        print("====================================================================\n")
        async with aclosing(await s.get(URL.replace("20", "100"), stream=True)) as r:
            async for chunk in r.aiter_content():
                print("Status: ", r.status_code)
                assert r.status_code == 200
                print("CHUNK", chunk)


asyncio.run(async_examples())
