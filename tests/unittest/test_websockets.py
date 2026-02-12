from curl_cffi.requests import AsyncSession, Session, WebSocket
from curl_cffi.requests.websockets import CurlWsFlag


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


def test_receive_large_messages(ws_server):
    ws = WebSocket()
    ws.connect(ws_server.url)
    for _ in range(10):
        ws.send("*" * 10000)
    for _ in range(10):
        buffer, _ = ws.recv()
        assert len(buffer) == 10000
    ws.close()


def test_receive_large_messages_run_forever(ws_server):
    def on_open(ws: WebSocket):
        ws.send("*" * 10000)

    chunk_counter = 0

    def on_data(ws: WebSocket, data, frame):
        nonlocal chunk_counter
        if frame.flags & CurlWsFlag.CLOSE:
            return
        chunk_counter += 1

    message = ""

    def on_message(ws: WebSocket, msg):
        nonlocal message
        message = msg
        # Gracefully close the connection to exit the run_forever loop
        ws.send("", CurlWsFlag.CLOSE)

    ws = WebSocket(
        on_open=on_open,
        on_data=on_data,
        on_message=on_message,
    )
    ws.run_forever(ws_server.url)

    assert chunk_counter >= 1
    assert len(message) == 10000


def test_on_data_callback(ws_server):
    on_data_called = False

    def on_data(ws: WebSocket, data, frame):
        nonlocal on_data_called
        on_data_called = True

    ws = WebSocket(on_data=on_data)
    ws.connect(ws_server.url)

    ws.send("Hello")
    ws.recv()
    assert on_data_called is False
    ws.close()


async def test_hello_twice_async(ws_server):
    async with AsyncSession() as s, s.ws_connect(ws_server.url) as ws:
        await ws.send(b"Bar")
        reply, _ = await ws.recv()

        for _ in range(10):
            await ws.send_str("Bar")
            reply = await ws.recv_str()
            assert reply == "Bar"
