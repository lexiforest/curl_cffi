from __future__ import annotations

import warnings
from contextlib import suppress
from typing import Any

from ._wrapper import ffi, lib
from .const import CurlECode, CurlMOpt
from .curl import DEFAULT_CACERT, Curl, CurlError
from .utils import CurlCffiWarning

CURL_POLL_NONE = 0
CURL_POLL_IN = 1
CURL_POLL_OUT = 2
CURL_POLL_INOUT = 3
CURL_POLL_REMOVE = 4

CURL_SOCKET_TIMEOUT = -1
CURL_SOCKET_BAD = -1

CURL_CSELECT_IN = 0x01
CURL_CSELECT_OUT = 0x02
CURL_CSELECT_ERR = 0x04

CURLMSG_DONE = 1

__all__ = [
    "BaseAsyncCurl",
    "CURL_SOCKET_BAD",
    "CURL_SOCKET_TIMEOUT",
    "CURL_POLL_IN",
    "CURL_POLL_OUT",
    "CURL_POLL_REMOVE",
    "CURL_CSELECT_IN",
    "CURL_CSELECT_OUT",
    "CURL_CSELECT_ERR",
]


"""
libcurl provides an event-based system for multiple handles with the following API:

- curl_multi_socket_action, for detecting events
- curl_multi_info_read, for reading the transfer status

There are 2 callbacks:

- socket_function, set by CURLMOPT_SOCKETFUNCTION, will be called for socket events.
- timer_function, set by CURLMOPT_TIMERFUNCTION, will be called when timeouts happen.

And it works like the following:

Set up handles, callbacks first.

When started, curl_multi_socket_action should be called to start everything.

If there are data in/out, libcurl calls the socket_function callback, and it sets up
`process_data` as asyncio loop reader/writer function. `process_data` will call
curl_multi_info_read to determine whether a certain `await perform` has finished.

When idle, libcurl will call the timer_function callback, which sets up a later call
for socket_action to detect events.
"""


@ffi.def_extern()
def timer_function(curlm, timeout_ms: int, clientp: Any) -> int:
    """
    see: https://curl.se/libcurl/c/CURLMOPT_TIMERFUNCTION.html
    """
    async_curl = ffi.from_handle(clientp)

    # Cancel the timer anyway, if it's -1, yes, libcurl says it should be cancelled.
    # If not, to add a new timer, we need to cancel the old timer.
    if async_curl._timer:
        async_curl._timer.cancel()  # If already called, cancel does nothing.
        async_curl._timer = None
    if timeout_ms < 0:
        return 0

    # libcurl says to install a timer which calls socket_action on fire.
    async_curl._timer = async_curl.loop.call_later(
        timeout_ms / 1000,
        async_curl.process_data,
        CURL_SOCKET_TIMEOUT,  # -1
        CURL_POLL_NONE,  # 0
    )

    return 0


@ffi.def_extern()
def socket_function(curl, sockfd: int, what: int, clientp: Any, data: Any) -> int:
    """This callback is called when libcurl decides it's time to interact with certain
    sockets"""

    async_curl = ffi.from_handle(clientp)
    loop = async_curl.loop

    # Always remove and re-add fds
    if sockfd in async_curl._sockfds:
        loop.remove_reader(sockfd)
        loop.remove_writer(sockfd)

    # Need to read from the socket
    if what & CURL_POLL_IN:
        loop.add_reader(sockfd, async_curl.process_data, sockfd, CURL_CSELECT_IN)
        async_curl._sockfds.add(sockfd)

    # Need to write to the socket
    if what & CURL_POLL_OUT:
        loop.add_writer(sockfd, async_curl.process_data, sockfd, CURL_CSELECT_OUT)
        async_curl._sockfds.add(sockfd)

    # Need to remove the socket
    if what == CURL_POLL_REMOVE:
        async_curl._sockfds.remove(sockfd)

    return 0


class BaseAsyncCurl:
    """Shared logic for async curl backends."""

    def __init__(
        self,
        *,
        cacert: str = "",
        cancelled_errors: tuple[type[BaseException], ...] = (),
    ) -> None:
        self._curlm = lib.curl_multi_init()
        self._cacert = cacert or DEFAULT_CACERT
        self._curl2future: dict[Curl, Any] = {}
        self._curl2curl: dict[ffi.CData, Curl] = {}
        self._sockfds: set[int] = set()
        self._timer = None
        self._cancelled_errors = cancelled_errors
        self._setup()
        self._timeout_checker = self.create_task(self._force_timeout())

    def _setup(self) -> None:
        self.setopt(CurlMOpt.TIMERFUNCTION, lib.timer_function)
        self.setopt(CurlMOpt.SOCKETFUNCTION, lib.socket_function)
        self._self_handle = ffi.new_handle(self)
        self.setopt(CurlMOpt.SOCKETDATA, self._self_handle)
        self.setopt(CurlMOpt.TIMERDATA, self._self_handle)

    def create_future(self):  # pragma: no cover - overridden in subclasses
        raise NotImplementedError

    def create_task(self, coro):  # pragma: no cover - overridden in subclasses
        raise NotImplementedError

    async def sleep(self, seconds: float) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:
        """Close and cleanup running timers, readers, writers and handles."""
        self._timeout_checker.cancel()
        with suppress(*self._cancelled_errors):
            await self._timeout_checker

        for curl, future in self._curl2future.items():
            lib.curl_multi_remove_handle(self._curlm, curl._curl)
            if future and not future.done() and not future.cancelled():
                future.set_result(None)

        lib.curl_multi_cleanup(self._curlm)
        self._curlm = None

        for sockfd in self._sockfds:
            self.loop.remove_reader(sockfd)
            self.loop.remove_writer(sockfd)

        if self._timer:
            self._timer.cancel()

    async def _force_timeout(self) -> None:
        """Safeguard against missing signals from curl."""
        while True:
            if not self._curlm:
                break
            self.process_data(CURL_SOCKET_TIMEOUT, CURL_POLL_NONE)
            await self.sleep(0.1)

    def add_handle(self, curl: Curl):
        """Add a curl handle to be managed by curl_multi."""
        curl._ensure_cacert()
        errcode = lib.curl_multi_add_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        future = self.create_future()
        self._curl2future[curl] = future
        self._curl2curl[curl._curl] = curl
        # Kick the state machine so timeouts/IO get scheduled immediately.
        self.process_data(CURL_SOCKET_TIMEOUT, CURL_POLL_NONE)
        return future

    def socket_action(self, sockfd: int, ev_bitmask: int) -> int:
        running_handle = ffi.new("int *")
        errcode = lib.curl_multi_socket_action(
            self._curlm, sockfd, ev_bitmask, running_handle
        )
        self._check_error(errcode)
        return running_handle[0]

    def process_data(self, sockfd: int, ev_bitmask: int) -> None:
        if not self._curlm:
            warnings.warn(
                "Curlm already closed! quitting from process_data",
                CurlCffiWarning,
                stacklevel=2,
            )
            return

        self.socket_action(sockfd, ev_bitmask)

        msg_in_queue = ffi.new("int *")
        while True:
            try:
                curl_msg = lib.curl_multi_info_read(self._curlm, msg_in_queue)
                if curl_msg == ffi.NULL:
                    break
                if curl_msg.msg == CURLMSG_DONE:
                    curl = self._curl2curl[curl_msg.easy_handle]
                    retcode = curl_msg.data.result
                    if retcode == 0:
                        self.set_result(curl)
                    else:
                        self.set_exception(curl, curl._get_error(retcode, "perform"))
                else:
                    print("NOT DONE")  # Will not reach, for nothing else being defined.
            except Exception:
                warnings.warn(
                    "Unexpected curl multi state in process_data, "
                    "please open an issue on GitHub\n",
                    CurlCffiWarning,
                    stacklevel=2,
                )

    def _pop_future(self, curl: Curl):
        errcode = lib.curl_multi_remove_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        self._curl2curl.pop(curl._curl, None)
        return self._curl2future.pop(curl, None)

    def remove_handle(self, curl: Curl) -> None:
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.cancel()

    def set_result(self, curl: Curl) -> None:
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.set_result(None)

    def set_exception(self, curl: Curl, exception: BaseException) -> None:
        future = self._pop_future(curl)
        if future and not future.done() and not future.cancelled():
            future.set_exception(exception)

    def _check_error(self, errcode: int, *args: Any) -> None:
        if errcode == CurlECode.OK:
            return
        errmsg = lib.curl_multi_strerror(errcode)
        action = " ".join([str(a) for a in args])
        raise CurlError(
            f"Failed in {action}, multi: ({errcode}) {errmsg}. "
            "See https://curl.se/libcurl/c/libcurl-errors.html first for more "
            "details. Please open an issue on GitHub to help debug this error.",
        )

    def setopt(self, option, value):
        """Wrapper around curl_multi_setopt."""
        if option in (
            CurlMOpt.PIPELINING,
            CurlMOpt.MAXCONNECTS,
            CurlMOpt.MAX_HOST_CONNECTIONS,
            CurlMOpt.MAX_PIPELINE_LENGTH,
            CurlMOpt.MAX_TOTAL_CONNECTIONS,
            CurlMOpt.MAX_CONCURRENT_STREAMS,
        ):
            c_value = ffi.new("long*", value)
        else:
            c_value = value
        return lib.curl_multi_setopt(self._curlm, option, c_value)
