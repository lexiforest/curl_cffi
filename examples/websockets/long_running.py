from curl_cffi import WebSocket

msg_count = 0


def on_message(ws: WebSocket, message: str | bytes):
    global msg_count

    print("------------------------------------------------------")
    print(message)
    print("======================================================")

    msg_count += 1
    if msg_count >= 100:
        ws.close()


def on_error(ws: WebSocket, error: Exception):
    print(error)


def on_open(ws: WebSocket):
    print(
        "For websockets, you need to set $wss_proxy environment variable!\n"
        "$https_proxy will not work!"
    )
    print(">>> Websocket open!")


def on_close(ws: WebSocket, code: int, reason: str):
    print(f"<<< Websocket closed! code: {code}, reason: {reason}, clean: {code in (1000, 1001)}")


ws = WebSocket(
    on_open=on_open,
    on_close=on_close,
    on_message=on_message,
    on_error=on_error,
)
ws.run_forever("wss://api.gemini.com/v1/marketdata/BTCUSD")
