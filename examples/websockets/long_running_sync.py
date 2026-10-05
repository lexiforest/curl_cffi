#!/usr/bin/env python3
import curl_cffi


def main() -> None:
    """Long running WSS example synchronously"""
    with curl_cffi.Session() as session:
        with session.ws_connect(
            "wss://api.gemini.com/v1/marketdata/BTCUSD", impersonate="chrome"
        ) as ws:
            print(
                "For websockets, you need to set $wss_proxy environment variable!\n"
                "$https_proxy will not work!"
            )
            print(">>> Websocket open!")

            try:
                for message in ws:
                    print(message)
            except KeyboardInterrupt:
                pass

        print("<<< Websocket closed!")


if __name__ == "__main__":
    main()
