import asyncio
from curl_cffi.const import CurlECode, CurlWsFlag
from curl_cffi.curl import CurlError


class WebSocket:
    def __init__(self, session, curl):
        self.session = session
        self.curl = curl
        self._loop = None

    def recv_fragment(self):
        return self.curl.ws_recv()

    def recv(self):
        chunks = []
        # TODO use select here
        while True:
            try:
                chunk, frame = self.curl.ws_recv()
                chunks.append(chunk)
                if frame.bytesleft == 0:
                    break
            except CurlError as e:
                if e.code == CurlECode.AGAIN:
                    pass
                else:
                    raise

        return b"".join(chunks)

    def send(self, payload: bytes, flags: CurlWsFlag = CurlWsFlag.BINARY):
        return self.curl.ws_send(payload, flags)

    def close(self):
        # FIXME how to reset. or can a curl handle connect to two websockets?
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
        self.session.push_curl(curl)
