import asyncio

import curl_cffi


async def main():
    async with curl_cffi.AsyncSession() as s:
        r = await s.get("https://httpbin.org/headers")
        print(r.text)

        r = await s.get("https://httpbin.org/stream/20", stream=True)
        async for chunk in r.aiter_content():
            print(chunk)


if __name__ == "__main__":
    asyncio.run(main())
