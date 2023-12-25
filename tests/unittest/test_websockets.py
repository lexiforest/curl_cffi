from curl_cffi.requests import Session


def test_websocket(ws_server):
    with Session() as s:
        s.ws_connect(ws_server.url)
