from __future__ import annotations

from contextlib import suppress
from typing import Any, Optional

try:
    import trio
except ImportError as exc:  # pragma: no cover - imported only when trio is needed.
    raise ImportError(
        "Trio support requires the 'trio' package. Install it with: pip install trio"
    ) from exc

from .async_base import BaseAsyncCurl

__all__ = ["TrioAsyncCurl"]

_NO_RESULT = object()


class TrioFuture:
    """Trio shim for asyncio.Future, based on trio.Event"""

    def __init__(self) -> None:
        self._done = trio.Event()
        self._result: Any = _NO_RESULT
        self._exception: Optional[BaseException] = None
        self._cancelled = False

    def cancel(self) -> None:
        if self._done.is_set():
            return
        self._cancelled = True
        self._done.set()

    def cancelled(self) -> bool:
        return self._cancelled

    def done(self) -> bool:
        return self._done.is_set()

    def set_result(self, result: Any) -> None:
        if self._done.is_set():
            return
        self._result = result
        self._done.set()

    def set_exception(self, exception: BaseException) -> None:
        if self._done.is_set():
            return
        self._exception = exception
        self._done.set()

    async def _wait(self) -> Any:
        await self._done.wait()
        if self._cancelled:
            raise trio.Cancelled()
        if self._exception is not None:
            raise self._exception
        if self._result is _NO_RESULT:
            return None
        return self._result

    def __await__(self):
        return self._wait().__await__()


class TrioTask:
    def __init__(self, coro) -> None:
        self._cancel_scope = trio.CancelScope()
        self._done = trio.Event()
        self._exception: Optional[BaseException] = None
        self._result: Any = _NO_RESULT
        self._callbacks: list[Any] = []
        trio.lowlevel.spawn_system_task(self._runner, coro)

    async def _runner(self, coro) -> None:
        try:
            with self._cancel_scope:
                self._result = await coro
        except BaseException as exc:
            self._exception = exc
        finally:
            self._done.set()
            for callback in self._callbacks:
                with suppress(Exception):
                    callback(self)

    def cancel(self) -> None:
        self._cancel_scope.cancel()

    def add_done_callback(self, callback) -> None:
        if self._done.is_set():
            callback(self)
            return
        self._callbacks.append(callback)

    async def _wait(self) -> Any:
        await self._done.wait()
        if isinstance(self._exception, trio.Cancelled):
            return None
        if self._exception is not None:
            raise self._exception
        if self._result is _NO_RESULT:
            return None
        return self._result

    def __await__(self):
        return self._wait().__await__()


class TrioTimerHandle:
    def __init__(self, delay: float, callback, *args: Any) -> None:
        self._cancel_scope = trio.CancelScope()
        trio.lowlevel.spawn_system_task(self._runner, delay, callback, args)

    async def _runner(self, delay: float, callback, args) -> None:
        with self._cancel_scope, suppress(trio.Cancelled):
            await trio.sleep(delay)
            callback(*args)

    def cancel(self) -> None:
        self._cancel_scope.cancel()


class TrioFdWatcher:
    def __init__(self, wait_fn, fd: int, callback, args: tuple[Any, ...]) -> None:
        self._cancel_scope = trio.CancelScope()
        trio.lowlevel.spawn_system_task(self._runner, wait_fn, fd, callback, args)

    async def _runner(self, wait_fn, fd: int, callback, args) -> None:
        with self._cancel_scope:
            while True:
                try:
                    await wait_fn(fd)
                except trio.Cancelled:
                    return
                except (OSError, trio.ClosedResourceError):
                    return
                callback(*args)

    def cancel(self) -> None:
        self._cancel_scope.cancel()


class TrioAsyncCurl(BaseAsyncCurl):
    """Wrapper around curl_multi handle to provide Trio support. It uses the libcurl
    socket_action APIs."""

    def __init__(self, cacert: str = "") -> None:
        """
        Args:
            cacert: CA cert path to use, by default, certs from ``certifi`` are used.
        """
        self._readers: dict[int, TrioFdWatcher] = {}
        self._writers: dict[int, TrioFdWatcher] = {}
        super().__init__(cacert=cacert, cancelled_errors=(trio.Cancelled,))

    @property
    def loop(self) -> TrioAsyncCurl:
        """Expose a loop-like interface to reuse the existing callbacks."""
        return self

    def add_reader(self, fd: int, callback, *args: Any) -> None:
        if fd in self._readers:
            self._readers[fd].cancel()
        self._readers[fd] = TrioFdWatcher(
            trio.lowlevel.wait_readable, fd, callback, args
        )

    def add_writer(self, fd: int, callback, *args: Any) -> None:
        if fd in self._writers:
            self._writers[fd].cancel()
        self._writers[fd] = TrioFdWatcher(
            trio.lowlevel.wait_writable, fd, callback, args
        )

    def remove_reader(self, fd: int) -> None:
        watcher = self._readers.pop(fd, None)
        if watcher:
            watcher.cancel()

    def remove_writer(self, fd: int) -> None:
        watcher = self._writers.pop(fd, None)
        if watcher:
            watcher.cancel()

    def call_later(self, delay: float, callback, *args: Any) -> TrioTimerHandle:
        return TrioTimerHandle(delay, callback, *args)

    def create_task(self, coro) -> TrioTask:
        return TrioTask(coro)

    def create_future(self) -> TrioFuture:
        return TrioFuture()

    async def sleep(self, seconds: float) -> None:
        await trio.sleep(seconds)
