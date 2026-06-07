#!/usr/bin/env python3
import asyncio
import json
from typing import cast

from curl_cffi import AsyncSession, Response


async def main() -> None:
    async with AsyncSession[Response](impersonate="chrome") as s:
        print("Connecting to Coinbase Pro...")

        async with s.ws_connect("wss://ws-feed.exchange.coinbase.com") as ws:
            # Send Subscription Request
            subscribe_msg: dict[str, str | list[str]] = {
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["ticker"],
            }
            print(f">>> Subscribing: {subscribe_msg['product_ids']}")
            await ws.send_json(payload=subscribe_msg)

            async for msg in ws:
                data: dict[str, object] = cast(dict[str, object], json.loads(msg))

                if data.get("type") == "subscriptions":
                    print("<<< Subscription confirmed!")
                    continue

                if data.get("type") == "ticker":
                    print(f"Ticker Update: BTC is at ${data.get('price')}")
                    # Just get one price update then exit
                    break


asyncio.run(main())
