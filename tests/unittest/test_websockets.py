from curl_cffi.requests import AsyncSession, WebSocket, Session


def test_websocket(ws_server):
    ws = WebSocket()
    ws.connect(ws_server.url)

    # deprecated
    with Session() as s:
        s.ws_connect(ws_server.url)


def test_hello(ws_server):
    ws = WebSocket()
    ws.connect(ws_server.url)
    ws.send(b"Foo me once")
    content, _ = ws.recv()
    assert content == b"Foo me once"

    # deprecated
    with Session() as s:
        ws = s.ws_connect(ws_server.url)
        ws.send(b"Foo me once")
        content, _ = ws.recv()
        assert content == b"Foo me once"


def test_hello_twice(ws_server):
    ws = WebSocket()
    ws.connect(ws_server.url)

    ws.send(b"Bar")
    reply, _ = ws.recv()

    for _ in range(10):
        ws.send_str("Bar")
        reply = ws.recv_str()
        assert reply == "Bar"

    with Session() as s:
        ws = s.ws_connect(ws_server.url)
        ws.send(b"Foo me once")
        content, _ = ws.recv()
        assert content == b"Foo me once"


async def test_hello_twice_async(ws_server):
    async with AsyncSession() as s:
        ws = await s.ws_connect(ws_server.url)

        await ws.send(b"Bar")
        reply, _ = await ws.recv()

        for _ in range(10):
            await ws.send_str("Bar")
            reply = await ws.recv_str()
            assert reply == "Bar"
