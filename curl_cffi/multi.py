import warnings
from collections.abc import Callable
from typing import Any

from ._wrapper import ffi, lib
from .const import CurlECode, CurlMOpt
from .curl import DEFAULT_CACERT, Curl, CurlError
from .utils import CurlCffiWarning
from enum import IntFlag, IntEnum


class CurlPoll(IntFlag):
    NONE = 0
    IN = 1
    OUT = 2
    INOUT = 3
    REMOVE = 4

    # Aliasing for less confusion for
    # those using selectors.
    READ = IN
    WRITE = OUT

class CurlSelect(IntEnum):
    IN = 0x01
    OUT = 0x02
    ERR = 0x04

CURL_SOCKET_TIMEOUT = -1
CURL_SOCKET_BAD = -1

CURLMSG_DONE = 1

CURLPIPE_NOTHING = 0
CURLPIPE_HTTP1 = 1  # deprecated
CURLPIPE_MULTIPLEX = 2


@ffi.def_extern()
def timer_function(curlm, timeout_ms: int, clientp: Any) -> int:
    """
    see: https://curl.se/libcurl/c/CURLMOPT_TIMERFUNCTION.html
    """
    multi: CurlMulti = ffi.from_handle(clientp)
    try:
        multi._timer_func(timeout_ms)
        return 0
    except Exception as e:
        multi._callback_err = e
        return -1


@ffi.def_extern()
def socket_function(curl, sockfd: int, what: int, clientp: Any, data: Any) -> int:
    """This callback is called when libcurl decides it's time to interact with certain
    sockets"""
    multi: CurlMulti = ffi.from_handle(clientp)
    try:
        multi._socket_func(sockfd, CurlPoll(what))
        return 0
    except Exception:
        # mark that we failed.
        return -1


class CurlMulti:
    """A wrapper around curl_multi for writing your own
    callbacks for wrapping with your own asynchronous extensions.
    """
    def __init__(
        self,
        socket_func: Callable[[int, CurlPoll], None],
        timer_func: Callable[[int], None],
        cacert: str = "",
    ):
        """
        Parameters:
            socket_func: Socket function callback, if an exception is raised
                in this callback curl-cffi will handle it.
            timer_func: Timer function callback which stores a 
                timeout in milliseconds. if an exception is raised
                in this callback curl-cffi will handle it.
            cacert: CA cert path to use, by default, certs from ``certifi`` are used.

        """
        self._callback_err: Exception | None = None
        self._curlm = lib.curl_multi_init()
        self._socket_func = socket_func
        self._timer_func = timer_func
        self._cacert = cacert or DEFAULT_CACERT
        self._handles: dict[
            Curl, Callable[[Curl | None, BaseException | None], None]
        ] = {}
        self._pointer_to_curl: dict[ffi.CData, Curl] = {}
    

    def _check_error(self, errcode: int, *args):
        if errcode == CurlECode.OK:
            return
        errmsg = lib.curl_multi_strerror(errcode)
        action = " ".join([str(a) for a in args])
        raise CurlError(
            f"Failed in {action}, multi: ({errcode}) {errmsg}. "
            "See https://curl.se/libcurl/c/libcurl-errors.html first for more "
            "details. Please open an issue on GitHub to help debug this error.",
        )

    def _setup(self) -> None:
        self.setopt(CurlMOpt.TIMERFUNCTION, lib.timer_function)
        self.setopt(CurlMOpt.SOCKETFUNCTION, lib.socket_function)
        self._self_handle = ffi.new_handle(self)
        self.setopt(CurlMOpt.SOCKETDATA, self._self_handle)
        self.setopt(CurlMOpt.TIMERDATA, self._self_handle)
        # self.setopt(CurlMOpt.PIPELINING, CURLPIPE_NOTHING)
    
    def cancel(self) -> None:
        """Cancells all queued Curl handles."""
        for curl, cb in self._handles.items():
            lib.curl_multi_remove_handle(self._curlm, curl._curl)
            # Notify that the user should cancel waiting or pending objects.
            cb(None, None)
        # Cleanse handles
        self._handles.clear()
        self._pointer_to_curl.clear()

    def _remove_handle(self, curl: Curl):
        errcode = lib.curl_multi_remove_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        self._pointer_to_curl.pop(curl._curl, None)
        return self._handles.pop(curl, None)


    def _set_result(self, curl: Curl) -> None:
        func = self._remove_handle(curl)
        if func is not None:
            func(curl, None)

    def _set_exception(self, curl: Curl, error: BaseException) -> None:
        func = self._remove_handle(curl)
        if func is not None:
            func(curl, error)


    def cleanup(self) -> None:
        """Deallocates C Pointer and cleans out the pending items."""
        if self._handles:
            # cleanup pending objects
            self.cancel()

        # Cleanup curl_multi handle
        lib.curl_multi_cleanup(self._curlm)
        self._curlm = None


    def add_handle(self, curl: Curl, callback: Callable[[Curl | None], None]):
        """
        Adds a handle along with a callback to call for when the 
        object is considered as being finished.
        """
        curl._ensure_cacert()
        errcode = lib.curl_multi_add_handle(self._curlm, curl._curl)
        self._check_error(errcode)
        self._handles[curl] = callback
        self._pointer_to_curl[curl._curl] = curl

    def socket_action(self, sockfd: int, ev_bitmask: int) -> int:
        """wrapper for curl_multi_socket_action,
        returns the number of running curl handles."""
        running_handle = ffi.new("int *")
        errcode = lib.curl_multi_socket_action(
            self._curlm, sockfd, ev_bitmask, running_handle
        )
        self._check_error(errcode)
        return running_handle[0]

    def process_timeout(self):
        """Signals CurlMulti to process the timeout action."""
        self.socket_action(CURL_SOCKET_TIMEOUT, CurlPoll.NONE)
        
    def process_data(self, sockfd: int, ev_bitmask: int):
        """
        Calls curl_multi_info_read to read data for given socket.
        This function can raise any exception from the callbacks
        made if any handles were perviously made.
        """
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
            # NOTE: Unlike AsyncCurl, the end developer must
            # take care of any exceptions raised as it is now 
            # their responsibility. The callbacks made by the end
            # developer play a key role if something fails.
            curl_msg = lib.curl_multi_info_read(self._curlm, msg_in_queue)
            # NULL is returned as a signal that no more to be get at this point
            if curl_msg == ffi.NULL:
                break
            if curl_msg.msg == CURLMSG_DONE:
                curl = self._pointer_to_curl[curl_msg.easy_handle]
                retcode = curl_msg.data.result
                if retcode == 0:
                    self._set_result(curl)
                else:
                    self._set_exception(curl, curl._get_error(retcode, "perform"))
    
    def setopt(self, option: int | CurlMOpt, value: Any):
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
    



