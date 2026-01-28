#!/usr/bin/env python3
import asyncio
import json
from typing import cast

from curl_cffi import AsyncSession, Response


async def main() -> None:
    async with AsyncSession[Response](impersonate="chrome") as s:
        print("Connecting to Binance Stream...")

        async with s.ws_connect("wss://stream.binance.com:9443/ws/btcusdt@trade") as ws:
            print(">>> Connected! Reading first 5 trades...")

            # Counter to stop the infinite stream
            count = 0
            async for msg in ws:
                # Parse JSON payload
                data: dict[str, object] = cast(dict[str, object], json.loads(msg))
                print(f"Trade: ${data['p']} (Qty: {data['q']})")

                count += 1
                if count >= 5:
                    break

            print("<<< Closing connection.")


asyncio.run(main())
