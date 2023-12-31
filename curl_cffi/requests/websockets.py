from typing import Callable, Optional, Tuple
import asyncio
from curl_cffi.const import CurlECode, CurlWsFlag
from curl_cffi.curl import CurlError


ON_MESSAGE_T = Callable[["WebSocket", bytes], None]
ON_ERROR_T = Callable[["WebSocket", CurlError], None]
ON_OPEN_T = Callable[["WebSocket"], None]
ON_CLOSE_T = Callable[["WebSocket"], None]


class WebSocket:
    def __init__(
        self,
        session,
        curl,
        on_message: Optional[ON_MESSAGE_T] = None,
        on_error: Optional[ON_ERROR_T] = None,
        on_open: Optional[ON_OPEN_T] = None,
        on_close: Optional[ON_CLOSE_T] = None,
    ):
        self.session = session
        self.curl = curl
        self.on_message = on_message
        self.on_error = on_error
        self.on_open = on_open
        self.on_close = on_close
        self.keep_running = True
        self._loop = None

    def recv_fragment(self):
        return self.curl.ws_recv()

    def recv(self) -> Tuple[bytes, int]:
        """
        Receive a frame as bytes.

        libcurl split frames into fragments, so we have to collect all the chunks for
        a frame.
        """
        chunks = []
        flags = 0
        # TODO use select here
        while True:
            try:
                chunk, frame = self.curl.ws_recv()
                flags = frame.flags
                chunks.append(chunk)
                if frame.bytesleft == 0 and flags & CurlWsFlag.CONT == 0:
                    break
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    pass
                else:
                    raise

        return b"".join(chunks), flags

    def send(self, payload: bytes, flags: CurlWsFlag = CurlWsFlag.BINARY):
        """Send a data frame"""
        return self.curl.ws_send(payload, flags)

    def run_forever(self):
        """
        libcurl automatically handles pings and pongs.

        ref: https://curl.se/libcurl/c/libcurl-ws.html
        """
        if self.on_open:
            self.on_open(self)
        try:
            # Keep reading the messages and invoke callbacks
            while self.keep_running:
                try:
                    msg, flags = self.recv()
                    if self.on_message:
                        self.on_message(self, msg)
                    if flags & CurlWsFlag.CLOSE:
                        self.keep_running = False
                except CurlError as e:
                    if self.on_error:
                        self.on_error(self, e)
        finally:
            if self.on_close:
                self.on_close(self)

    def close(self, msg: bytes = b""):
        # FIXME how to reset, or can a curl handle connect to two websockets?
        self.send(msg, CurlWsFlag.CLOSE)
        self.keep_running = False
        self.curl.close()

    @property
    def loop(self):
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        return self._loop

    async def arecv(self):
        return await self.loop.run_in_executor(None, self.recv)

    async def asend(self, payload: bytes, flags: CurlWsFlag = CurlWsFlag.BINARY):
        return await self.loop.run_in_executor(None, self.send, payload, flags)

    async def aclose(self):
        await self.loop.run_in_executor(None, self.close)
        self.curl.reset()
        self.session.push_curl(self.curl)
