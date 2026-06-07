#!/usr/bin/env python3
import asyncio

from curl_cffi import AsyncSession, Response


async def main() -> None:
    """Test basic echo"""
    async with AsyncSession[Response]() as s:
        print("Connecting to Postman Echo...")
        async with s.ws_connect("wss://ws.postman-echo.com/raw") as ws:
            message = "Hello from curl_cffi!"
            print(f">>> Sending: {message}")
            await ws.send_str(payload=message)

            response: str = await ws.recv_str()
            print(f"<<< Received: {response}")

            assert message == response
            print("Echo test passed!")


asyncio.run(main())
