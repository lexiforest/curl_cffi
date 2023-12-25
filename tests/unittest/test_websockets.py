from curl_cffi.requests import Session


def test_websocket(ws_server):
    with Session() as s:
        s.ws_connect(ws_server.url)


def test_hello(ws_server):
    with Session() as s:
        ws = s.ws_connect(ws_server.url)
        ws.send(b"foo")
        content = ws.recv()
        assert content == b"foo"
