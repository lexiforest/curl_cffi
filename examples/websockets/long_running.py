from curl_cffi.requests import Session, WebSocket

msg_count = 0


def on_message(ws: WebSocket, message):
    global msg_count

    print("------------------------------------------------------")
    print(message)
    print("======================================================")

    msg_count += 1
    if msg_count >= 100:
        ws.close()


def on_error(ws: WebSocket, error):
    print(error)


def on_open(ws: WebSocket):
    print(
        "For websockets, you need to set $wss_proxy environment variable!\n"
        "$https_proxy will not work!"
    )
    print(">>> Websocket open!")


def on_close(ws: WebSocket):
    print("<<< Websocket closed!")


with Session() as s:
    ws = s.ws_connect(
        "wss://api.gemini.com/v1/marketdata/BTCUSD",
        on_open=on_open,
        on_close=on_close,
        on_message=on_message,
        on_error=on_error,
    )
    ws.run_forever()
