from curl_cffi.const import CurlECode, CurlWsFlag
from curl_cffi.curl import CurlError


class WebSocket:
    def __init__(self, session):
        self.session = session

    @property
    def c(self):
        return self.session.curl

    def recv_fragment(self):
        return  self.c.ws_recv()

    def recv(self):
        chunks = []
        # TODO use select here
        while True:
            try:
                chunk, frame = self.c.ws_recv()
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
        return self.c.ws_send(payload, flags)

    def close(self):
        return self.c.close()


class AsyncWebSocket:
    def __init__(self, session, curl):
        self.session = session
        self.curl = curl

    async def recv(self):
        return await self.curl.ws_recv()

    async def send(self):
        return await self.curl.ws_send()

    async def close(self):
        return await self.curl.close()
