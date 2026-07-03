#!/usr/bin/env python3
import json
from typing import Final, cast

from curl_cffi import Response, Session


def main() -> None:
    with Session[Response](impersonate="chrome") as s:
        print("Connecting to Binance Stream...")
        max_trades: Final[int] = 20

        with s.ws_connect("wss://stream.binance.com:9443/ws/btcusdt@trade") as ws:
            print(f">>> Connected! Reading first {max_trades} trades...")

            for count, msg in enumerate[bytes](ws, start=1):
                # Parse JSON payload
                data: dict[str, object] = cast(dict[str, object], json.loads(msg))
                print(f"Trade {count}: ${data['p']} (Qty: {data['q']})")

                # Counter to stop the infinite stream
                if count >= max_trades:
                    break

            print("<<< Closing connection.")


if __name__ == "__main__":
    main()
