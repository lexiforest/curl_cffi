#!/usr/bin/env python3
import json
from typing import cast

from curl_cffi import Response, Session


def main() -> None:
    with Session[Response](impersonate="chrome") as s:
        print("Connecting to Coinbase Pro...")

        with s.ws_connect(
            "wss://ws-feed.exchange.coinbase.com", impersonate="chrome"
        ) as ws:
            # Send Subscription Request
            subscribe_msg: dict[str, str | list[str]] = {
                "type": "subscribe",
                "product_ids": ["BTC-USD"],
                "channels": ["ticker"],
            }
            print(f">>> Subscribing: {subscribe_msg['product_ids']}")
            _ = ws.send_json(payload=subscribe_msg)

            for msg in ws:
                data: dict[str, object] = cast(dict[str, object], json.loads(msg))

                if data.get("type") == "subscriptions":
                    print("<<< Subscription confirmed!")
                    continue

                if data.get("type") == "ticker":
                    print(f"Ticker Update: BTC is at ${data.get('price')}")
                    # Just get one price update then exit
                    break


if __name__ == "__main__":
    main()
