from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterable, Awaitable, Callable, Iterable, Iterator
from contextlib import suppress
from io import SEEK_END, SEEK_SET, BytesIO
from typing import IO, TYPE_CHECKING, Any, Union, cast, final

from .._wrapper import ffi, lib
from ..aio import CURLMSG_DONE, check_multi_error
from ..curl import (
    CURL_READFUNC_PAUSE,
    CURL_WRITEFUNC_PAUSE,
    CURLPAUSE_CONT,
    CURLPAUSE_RECV,
    CURLPAUSE_SEND_CONT,
    Curl,
    CurlError,
)
from .exceptions import UnrewindableBodyError

if TYPE_CHECKING:
    from ..aio import AsyncCurl


RequestData = Union[
    dict[str, str],
    list[tuple[str, str]],
    str,
    BytesIO,
    bytes,
]
SyncRequestContent = Union[str, bytes, bytearray, IO[bytes], Iterable[bytes]]
RequestContent = Union[SyncRequestContent, AsyncIterable[bytes]]

_BODY_NOT_REWINDABLE = object()

# Upper bound for one blocking wait, so signals like Ctrl-C are handled promptly.
_POLL_INTERVAL_MS = 100


@final
class _StreamBody:
    """Pull-based body of a sync streaming response.

    The transfer runs on a private multi handle that is only driven from
    ``read()``, and stays paused while the caller holds a chunk, so libcurl reads
    from the socket only as fast as the body is consumed. Resuming from a pause
    also restarts libcurl's stall detection, the low speed timeout used for
    streams, which otherwise lags behind ``timeout`` by a few seconds.
    """

    def __init__(
        self, curl: Curl, run_blocking: Callable[[Callable[[], int]], int]
    ) -> None:
        self.curl = curl
        self._run_blocking = run_blocking
        self._multi: Any = None
        self._chunk: bytes | None = None
        self._paused = False
        self._done = False
        self._closed = False
        self._error: BaseException | None = None
        self._to_error: Callable[[CurlError], BaseException] | None = None
        # Guards the handles, except during the blocking poll, so that close() can
        # be called from another thread.
        self._lock = threading.Lock()
        self._polling = False

    def write(self, chunk: bytes) -> int:
        """``CURLOPT_WRITEFUNCTION``: hold one chunk, pause until it's read."""
        if self._chunk is not None:
            self._paused = True
            return CURL_WRITEFUNC_PAUSE
        self._chunk = chunk
        return len(chunk)

    def start(self, to_error: Callable[[CurlError], BaseException]) -> None:
        """Start the transfer and wait for the first body chunk or its end.

        Raises the transfer's error if it fails before any body is received.
        """
        self._to_error = to_error
        self.curl._ensure_cacert()
        self._multi = lib.curl_multi_init()
        check_multi_error(
            lib.curl_multi_add_handle(self._multi, self.curl._curl), "add_handle"
        )
        self._fill()
        if self._chunk is None and self._error is not None:
            raise self._error

    def read(self) -> bytes | None:
        """Return the next chunk, or ``None`` at the end of the body or once
        closed."""
        with self._lock:
            if self._closed:
                return None
            if self._chunk is None and not self._done and self._paused:
                self._paused = False
                # libcurl may hand over buffered data before this returns.
                self.curl.pause(CURLPAUSE_CONT)
        self._fill()
        with self._lock:
            if self._closed:
                return None
            chunk, self._chunk = self._chunk, None
        if chunk is not None:
            return chunk
        if self._error is not None:
            raise self._error
        return None

    def _fill(self) -> None:
        multi = self._multi
        running = ffi.new("int *")
        numfds = ffi.new("int *")

        def poll() -> int:
            try:
                return lib.curl_multi_poll(
                    multi, ffi.NULL, 0, _POLL_INTERVAL_MS, numfds
                )
            finally:
                # Also runs when a signal like Ctrl-C is raised right after the
                # poll, or on a worker thread whose caller already gave up, e.g.
                # on a gevent timeout, so a pending close() is completed here.
                with self._lock:
                    self._polling = False
                    if self._closed:
                        self._free()

        while True:
            with self._lock:
                if self._closed or self._chunk is not None or self._done:
                    break
                check_multi_error(lib.curl_multi_perform(multi, running), "perform")
                self._collect()
                if self._chunk is not None or self._done:
                    break
                self._polling = True
            check_multi_error(self._run_blocking(poll), "poll")
        with self._lock:
            if not (self._closed or self._done or self._paused):
                self._paused = True
                self.curl.pause(CURLPAUSE_RECV)

    def _collect(self) -> None:
        msgs = ffi.new("int *")
        while (msg := lib.curl_multi_info_read(self._multi, msgs)) != ffi.NULL:
            if msg.msg != CURLMSG_DONE:
                continue
            self._done = True
            error = self.curl._get_callback_exception()
            if error is None and msg.data.result != 0:
                assert self._to_error is not None
                error = self._to_error(self.curl._get_error(msg.data.result, "perform"))
            self._error = error

    def close(self) -> None:
        """Abort the transfer if it's still running, and free the handles.

        Can be called from another thread, a blocked ``read()`` then returns
        ``None``.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._polling:
                # The poller frees the handles once it returns.
                lib.curl_multi_wakeup(self._multi)
            else:
                self._free()

    def _free(self) -> None:
        if self._multi is not None:
            if self.curl._curl is not None:
                lib.curl_multi_remove_handle(self._multi, self.curl._curl)
            lib.curl_multi_cleanup(self._multi)
            self._multi = None
        self.curl.close()


@final
class _AsyncStreamBody:
    """Body of an async streaming response.

    The transfer runs on the session's ``AsyncCurl`` and pauses as soon as one
    chunk is waiting to be read, so at most one chunk is buffered ahead.
    """

    def __init__(self, curl: Curl, acurl: AsyncCurl) -> None:
        self.curl = curl
        self._acurl = acurl
        self._chunk: bytes | None = None
        self._paused = False
        self._done = False
        self._closed = False
        self._error: BaseException | None = None
        self._waiter: asyncio.Future[None] | None = None
        self._future: asyncio.Future[None] | None = None
        self._task: asyncio.Task[None] | None = None

    def write(self, chunk: bytes) -> int:
        """``CURLOPT_WRITEFUNCTION``: hold one chunk, pause until it's read."""
        if self._chunk is not None:
            self._paused = True
            return CURL_WRITEFUNC_PAUSE
        self._chunk = chunk
        self._wake()
        return len(chunk)

    async def start(
        self,
        to_error: Callable[[CurlError], BaseException],
        on_finish: Callable[[], Awaitable[None]],
    ) -> None:
        """Start the transfer and wait for the first body chunk or its end.

        Raises the transfer's error if it fails before any body is received.
        ``on_finish`` runs once the transfer is over, or aborted by ``close()``,
        but not before this returns, so the caller can still read the handle's
        infos.
        """
        try:
            future = self._future = self._acurl.add_handle(self.curl)
        except BaseException:
            await on_finish()
            raise
        started = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(
            self._run(future, started, to_error, on_finish)
        )
        try:
            await self._wait()
            if self._chunk is None and self._error is not None:
                raise self._error
        finally:
            started.set_result(None)

    async def _run(
        self,
        future: asyncio.Future[None],
        started: asyncio.Future[None],
        to_error: Callable[[CurlError], BaseException],
        on_finish: Callable[[], Awaitable[None]],
    ) -> None:
        try:
            # Unlike awaiting it, this doesn't raise when close() cancels the future.
            await asyncio.wait((future,))
            if not future.cancelled():
                error = future.exception()
                if isinstance(error, CurlError):
                    error = to_error(error)
                self._error = error
        finally:
            self._done = True
            self._wake()
            await started
            await on_finish()

    def _wake(self) -> None:
        waiter = self._waiter
        if waiter is not None and not waiter.done():
            waiter.set_result(None)

    async def _wait(self) -> None:
        while self._chunk is None and not (self._done or self._closed):
            self._waiter = asyncio.get_running_loop().create_future()
            try:
                await self._waiter
            finally:
                self._waiter = None

    async def read(self) -> bytes | None:
        """Return the next chunk, or ``None`` at the end of the body or once
        closed."""
        await self._wait()
        if self._closed:
            return None
        chunk = self._chunk
        if chunk is None:
            if self._error is not None:
                raise self._error
            return None
        self._chunk = None
        # The handle can't be unpaused once it left the multi, e.g. when the
        # session was closed.
        if self._paused and not cast(asyncio.Future, self._future).done():
            self._paused = False
            # libcurl may hand over buffered data before this returns.
            self.curl.pause(CURLPAUSE_CONT)
        return chunk

    def close(self) -> None:
        """Abort the transfer if it's still running. Cleanup completes in the
        background, await ``aclose()`` to wait for it."""
        self._closed = True
        self._wake()
        future = self._future
        # Nothing to abort once the transfer is over or the session closed it, and
        # a response collected after its loop closed can't abort anymore.
        if (
            future is not None
            and not future.done()
            and not future.get_loop().is_closed()
        ):
            self._acurl.remove_handle(self.curl)

    async def aclose(self) -> None:
        """Abort the transfer if it's still running, and wait for the cleanup."""
        self.close()
        if self._task is not None:
            await self._task


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

    __slots__ = ("_file", "_length", "_start")

    def __init__(self, file: Any) -> None:
        self._file = file
        self._length: int | None = None
        try:
            if hasattr(file, "seekable") and not file.seekable():
                raise OSError
            self._start: int | None = file.tell()
        except (AttributeError, OSError):
            self._start = None
        if self._start is not None:
            try:
                file.seek(0, SEEK_END)
                self._length = max(0, file.tell() - self._start)
            except (AttributeError, OSError):
                pass
            finally:
                try:
                    file.seek(self._start)
                except (AttributeError, OSError):
                    self._start = None
                    self._length = None

    @property
    def length(self) -> int | None:
        return self._length

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
