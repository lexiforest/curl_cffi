import queue
import warnings
from concurrent.futures import Future
from json import loads
from typing import Any, Awaitable, Dict, List, Optional

from .. import Curl
from .cookies import Cookies
from .errors import RequestsError
from .headers import Headers


def clear_queue(q: queue.Queue):
    with q.mutex:
        q.queue.clear()
        q.all_tasks_done.notify_all()
        q.unfinished_tasks = 0


class Request:
    """Representing a sent request."""

    def __init__(self, url: str, headers: Headers, method: str):
        self.url = url
        self.headers = headers
        self.method = method


class Response:
    """Contains information the server sends.

    Attributes:
        url: url used in the request.
        content: response body in bytes.
        text: response body in str.
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
        self.history: List[Dict[str, Any]] = []
        self.infos: Dict[str, Any] = {}
        self.queue: Optional[queue.Queue] = None
        self.stream_task: Optional[Future] = None
        self.astream_task: Optional[Awaitable] = None
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
        """Raise an error if status code is not in [200, 400)"""
        if not self.ok:
            raise RequestsError(f"HTTP Error {self.status_code}: {self.reason}")

    def iter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        iterate streaming content line by line, separated by ``\\n``.

        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        for chunk in self.iter_content(chunk_size=chunk_size, decode_unicode=decode_unicode):
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
        """
        iterate streaming content chunk by chunk in bytes.
        """
        if chunk_size:
            warnings.warn("chunk_size is ignored, there is no way to tell curl that.")
        if decode_unicode:
            raise NotImplementedError()

        assert self.queue and self.curl, "stream mode is not enabled."

        while True:
            chunk = self.queue.get()

            # re-raise the exception if something wrong happened.
            if isinstance(chunk, RequestsError):
                self.curl.reset()
                raise chunk

            # end of stream.
            if chunk is None:
                self.curl.reset()
                return

            yield chunk

    def json(self, **kw):
        """return a parsed json object of the content."""
        return loads(self.content, **kw)

    def close(self):
        """Close the streaming connection, only valid in stream mode."""

        if self.quit_now:
            self.quit_now.set()
        if self.stream_task:
            self.stream_task.result()

    async def aiter_lines(self, chunk_size=None, decode_unicode=False, delimiter=None):
        """
        iterate streaming content line by line, separated by ``\\n``.

        Copied from: https://requests.readthedocs.io/en/latest/_modules/requests/models/
        which is under the License: Apache 2.0
        """
        pending = None

        async for chunk in self.aiter_content(chunk_size=chunk_size, decode_unicode=decode_unicode):
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
        """
        iterate streaming content chunk by chunk in bytes.
        """
        if chunk_size:
            warnings.warn("chunk_size is ignored, there is no way to tell curl that.")
        if decode_unicode:
            raise NotImplementedError()

        assert self.queue and self.curl, "stream mode is not enabled."

        while True:
            chunk = await self.queue.get()

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
        """
        Return a decoded string.
        """
        return self._decode(await self.acontent())

    async def acontent(self) -> bytes:
        """wait and read the streaming content in one bytes object."""
        chunks = []
        async for chunk in self.aiter_content():
            chunks.append(chunk)
        return b"".join(chunks)

    async def aclose(self):
        """Close the streaming connection, only valid in stream mode."""

        if self.astream_task:
            await self.astream_task

    # It prints the status code of the response instead of
    # the object's memory location.
    def __repr__(self) -> str:
        return f"<Response [{self.status_code}]>"
