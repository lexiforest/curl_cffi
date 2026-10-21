from queue import Queue
from threading import Thread

import pytest
from websockets.sync.server import serve

from curl_cffi import AsyncSession, CurlOpt, CurlWsOption, Session, ffi

COMPRESSION_OPTIONS = {CurlOpt.WS_OPTIONS: CurlWsOption.PERMESSAGE_DEFLATE}
# 300,000 UTF-8 bytes exceed Curl._WS_RECV_BUFFER_SIZE (128 * 1024 bytes).
# The buffer holds decompressed data, so the echo requires at least three reads.
PAYLOAD = "hello " * 50000


@pytest.fixture
def compression_server():
    handshakes = Queue()

    def echo(ws):
        handshakes.put([extension.name for extension in ws.protocol.extensions])
        for message in ws:
            ws.send(message)

    with serve(echo, "127.0.0.1", 0, compression="deflate", close_timeout=1) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"ws://127.0.0.1:{server.socket.getsockname()[1]}", handshakes
        finally:
            server.shutdown()
            thread.join(timeout=5)


def test_compression_round_trip(compression_server):
    url, handshakes = compression_server
    with (
        Session() as session,
        session.ws_connect(url, curl_options=COMPRESSION_OPTIONS) as ws,
    ):
        assert handshakes.get(timeout=5) == ["permessage-deflate"]
        ws.send_str(PAYLOAD, timeout=5)
        assert ws.recv_str(timeout=5) == PAYLOAD


async def test_compression_round_trip_async(compression_server):
    url, handshakes = compression_server
    async with (
        AsyncSession() as session,
        session.ws_connect(url, curl_options=COMPRESSION_OPTIONS) as ws,
    ):
        assert handshakes.get(timeout=5) == ["permessage-deflate"]
        await ws.send_str(PAYLOAD, timeout=5)
        assert await ws.recv_str(timeout=5) == PAYLOAD


def test_frame_metadata_signed_bytesleft():
    frame = ffi.new("struct curl_ws_frame *", {"bytesleft": -1})
    assert frame.bytesleft == -1
