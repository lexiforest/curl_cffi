import warnings
from json import loads
from typing import Optional
import queue

from .. import Curl
from .headers import Headers
from .cookies import Cookies
from .errors import RequestsError


def clear_queue(q: queue.Queue):
    with q.mutex:
        q.queue.clear()
        q.all_tasks_done.notify_all()
        q.unfinished_tasks = 0


class Request:
    def __init__(self, url: str, headers: Headers, method: str):
        self.url = url
        self.headers = headers
        self.method = method


class Response:
    """Contains information the server sends.

    Attributes:
        url: url used in the request.
        content: response body in bytes.
        status_code: http status code.
        reason: http response reason, such as OK, Not Found.
        ok: is status_code in [200, 400)?
        headers: response headers.
        cookies: response cookies.
        elapsed: how many seconds the request cost.
        encoding: http body encoding.
        charset: alias for encoding.
        redirect_count: how many redirects happened.
        redirect_url: the final redirected url.
        http_version: http version used.
        history: history redirections, only headers are available.
    """

    def __init__(self, curl: Optional[Curl] = None, request: Optional[Request] = None):
        self.curl = curl
        self.request = request
        self.url = ""
        self.content = b""
        self.status_code = 200
        self.reason = "OK"
        self.ok = True
        self.headers = Headers()
        self.cookies = Cookies()
        self.elapsed = 0.0
        self.encoding = "utf-8"
        self.charset = self.encoding
        self.redirect_count = 0
        self.redirect_url = ""
        self.http_version = 0
        self.history = []
        self.infos = {}
        self.queue: Optional[queue.Queue] = None
        self.stream_task = None
        self.quit_now = None

    def _decode(self, content: bytes) -> str:
        try:
            return content.decode(self.charset, errors="replace")
        except (UnicodeDecodeError, LookupError):
            return content.decode("utf-8-sig")

    @property
    def text(self) -> str:
        return self._decode(self.content)

    def raise_for_status(self):
        if not self.ok:
            raise RequestsError(f"HTTP Error {self.status_code}: {self.reason}")

    def iter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        for chunk in self.iter_content(
            chunk_size=chunk_size, decode_unicode=decode_unicode
        ):
            if pending is not None:
                chunk = pending + chunk
            if delimiter:
                lines = chunk.split(delimiter)
            else:
                lines = chunk.splitlines()
            if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
                pending = lines.pop()
            else:
                pending = None

            yield from lines

        if pending is not None:
            yield pending

    def iter_content(self, chunk_size=None, decode_unicode=False):
        if chunk_size:
            warnings.warn("chunk_size is ignored, there is no way to tell curl that.")
        if decode_unicode:
            raise NotImplementedError()
        while True:
            chunk = self.queue.get()  # type: ignore

            # re-raise the exception if something wrong happened.
            if isinstance(chunk, RequestsError):
                self.curl.reset()  # type: ignore
                raise chunk

            # end of stream.
            if chunk is None:
                self.curl.reset()  # type: ignore
                return

            yield chunk

    def json(self, **kw):
        return loads(self.content, **kw)

    def close(self):
        self.quit_now.set()  # type: ignore
        self.stream_task.result()  # type: ignore

    async def aiter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        async for chunk in self.aiter_content(
            chunk_size=chunk_size, decode_unicode=decode_unicode
        ):
            if pending is not None:
                chunk = pending + chunk
            if delimiter:
                lines = chunk.split(delimiter)
            else:
                lines = chunk.splitlines()
            if lines and lines[-1] and chunk and lines[-1][-1] == chunk[-1]:
                pending = lines.pop()
            else:
                pending = None

            for line in lines:
                yield line

        if pending is not None:
            yield pending

    async def aiter_content(self, chunk_size=None, decode_unicode=False):
        if chunk_size:
            warnings.warn("chunk_size is ignored, there is no way to tell curl that.")
        if decode_unicode:
            raise NotImplementedError()

        while True:
            chunk = await self.queue.get()  # type: ignore

            # re-raise the exception if something wrong happened.
            if isinstance(chunk, RequestsError):
                await self.aclose()
                raise chunk

            # end of stream.
            if chunk is None:
                await self.aclose()
                return

            yield chunk

    async def atext(self) -> str:
        return self._decode(await self.acontent())

    async def acontent(self) -> bytes:
        chunks = []
        async for chunk in self.aiter_content():
            chunks.append(chunk)
        return b"".join(chunks)

    async def aclose(self):
        await self.stream_task  # type: ignore
