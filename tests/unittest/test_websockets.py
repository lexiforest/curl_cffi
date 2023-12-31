from curl_cffi.requests import Session


def test_websocket(ws_server):
    with Session() as s:
        s.ws_connect(ws_server.url)


def test_hello(ws_server):
    with Session() as s:
        ws = s.ws_connect(ws_server.url)
        ws.send(b"Foo me once")
        content, _ = ws.recv()
        assert content == b"Foo me once"


def test_hello_twice(ws_server):
    with Session() as s:
        w = s.ws_connect(ws_server.url)

        w.send(b"Bar")
        reply, _ = w.recv()

        for _ in range(10):
            w.send(b"Bar")
            reply, _ = w.recv()
            assert reply == b"Bar"
