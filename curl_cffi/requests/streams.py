from __future__ import annotations

import asyncio
import queue
from collections.abc import AsyncIterable, Iterable, Iterator
from contextlib import suppress
from io import SEEK_SET, BytesIO
from typing import IO, Any, Union, cast, final

from ..curl import CURL_READFUNC_PAUSE, CURLPAUSE_SEND_CONT, Curl
from .exceptions import UnrewindableBodyError


RequestData = Union[
    dict[str, str],
    list[tuple],
    str,
    BytesIO,
    bytes,
]
SyncRequestContent = Union[str, bytes, bytearray, IO[bytes], Iterable[bytes]]
RequestContent = Union[SyncRequestContent, AsyncIterable[bytes]]

STREAM_END = object()
_BODY_NOT_REWINDABLE = object()


def _peek_queue(q: queue.Queue, default=None):
    try:
        return q.queue[0]
    except IndexError:
        return default


def _peek_aio_queue(q: asyncio.Queue, default=None):
    try:
        return q._queue[0]  # type: ignore
    except IndexError:
        return default


def _capture_body_position(data: object | None, content: object | None):
    """Capture enough state to safely replay a request body after a failed attempt."""
    body = content if content is not None else data
    if not hasattr(body, "read"):
        if content is not None and isinstance(body, AsyncIterable):
            return None if body.__aiter__() is not body else _BODY_NOT_REWINDABLE
        if content is not None and isinstance(body, Iterable):
            return None if iter(body) is not body else _BODY_NOT_REWINDABLE
        return None
    try:
        if hasattr(body, "seekable") and not body.seekable():
            raise OSError
        return body.tell()
    except (AttributeError, OSError):
        return _BODY_NOT_REWINDABLE


def _rewind_body(body: object | None, position: object) -> None:
    if position is None:
        return
    if position is _BODY_NOT_REWINDABLE:
        raise UnrewindableBodyError("Unable to rewind streamed request body for retry")
    try:
        body.seek(position)
    except (AttributeError, OSError) as exc:
        raise UnrewindableBodyError(
            "Unable to rewind streamed request body for retry"
        ) from exc


@final
class _IterableReader:
    """Adapt a sync ``Iterable[bytes]`` to the ``read(size)`` interface that
    libcurl's read callback expects, buffering and slicing chunks to ``size``."""

    __slots__ = ("_it", "_buf")

    def __init__(self, iterable: Iterable[bytes]) -> None:
        self._it: Iterator[bytes] = iter(iterable)
        self._buf: bytearray = bytearray()

    def read(self, size: int) -> bytes:
        buf = self._buf
        while not buf:
            try:
                chunk = next(self._it)
            except StopIteration:
                return b""
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                raise TypeError("request body iterator must yield bytes")
            buf += chunk
        chunk = bytes(buf[:size])
        del buf[:size]
        return chunk


@final
class _FileReader:
    """Keep the starting offset of a file-like upload so libcurl can replay it."""

    __slots__ = ("_file", "_start")

    def __init__(self, file: Any) -> None:
        self._file = file
        try:
            if hasattr(file, "seekable") and not file.seekable():
                raise OSError
            self._start: int | None = file.tell()
        except (AttributeError, OSError):
            self._start = None

    @property
    def rewindable(self) -> bool:
        return self._start is not None and hasattr(self._file, "seek")

    def read(self, size: int) -> bytes:
        return self._file.read(size)

    def seek(self, offset: int, origin: int) -> int:
        if not self.rewindable:
            raise OSError("request body is not seekable")
        if origin == SEEK_SET:
            offset += cast(int, self._start)
        return self._file.seek(offset, origin)


@final
class _AsyncIterableReader:
    """Bridge an async byte iterable to libcurl's synchronous read callback."""

    def __init__(self, iterable: AsyncIterable[bytes], curl: Curl) -> None:
        self._iterable = iterable
        self._curl = curl
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
        self._buffer = bytearray()
        self._done = False
        self._paused = False
        self._exception: BaseException | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._produce())

    async def close(self) -> None:
        task = self._task
        if task is None:
            return
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    async def _produce(self) -> None:
        iterator = self._iterable.__aiter__()
        try:
            while True:
                try:
                    chunk = await iterator.__anext__()
                except StopAsyncIteration:
                    break
                if not isinstance(chunk, (bytes, bytearray, memoryview)):
                    raise TypeError("request body iterator must yield bytes")
                if not chunk:
                    continue
                await self._queue.put(bytes(chunk))
                self._resume()
        except asyncio.CancelledError:
            raise
        except BaseException as exc:
            self._exception = exc
        finally:
            aclose = getattr(iterator, "aclose", None)
            try:
                if aclose is not None:
                    await aclose()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:
                if self._exception is None:
                    self._exception = exc
            finally:
                self._done = True
                self._resume()

    def _resume(self) -> None:
        if self._paused:
            self._paused = False
            self._curl.pause(CURLPAUSE_SEND_CONT)

    def read(self, size: int) -> bytes | int:
        buffer = self._buffer
        if not buffer:
            try:
                buffer += self._queue.get_nowait()
            except asyncio.QueueEmpty:
                if self._done:
                    if self._exception is not None:
                        raise self._exception from None
                    return b""
                self._paused = True
                return CURL_READFUNC_PAUSE
        chunk = bytes(buffer[:size])
        del buffer[:size]
        return chunk
