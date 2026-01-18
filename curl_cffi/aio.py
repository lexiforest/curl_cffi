import asyncio
import sys
import warnings
from weakref import WeakKeyDictionary

from .async_base import (
    BaseAsyncCurl,
    CURL_CSELECT_IN,
    CURL_CSELECT_OUT,
    CURL_POLL_IN,
    CURL_POLL_OUT,
    CURL_POLL_REMOVE,
    CURL_SOCKET_TIMEOUT,
)
from .utils import CurlCffiWarning

__all__ = ["AsyncCurl"]

if sys.platform == "win32":
    # registry of asyncio loop : selector thread
    _selectors: WeakKeyDictionary = WeakKeyDictionary()
    PROACTOR_WARNING = """
    Proactor event loop does not implement add_reader family of methods required.
    Registering an additional selector thread for add_reader support.
    To avoid this warning use:
        asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    """

    def get_selector(
        asyncio_loop: asyncio.AbstractEventLoop,
    ) -> asyncio.AbstractEventLoop:
        """Get selector-compatible loop

        Returns an object with ``add_reader`` family of methods,
        either the loop itself or a SelectorThread instance.

        Workaround Windows proactor removal of *reader methods.
        """

        if asyncio_loop in _selectors:
            return _selectors[asyncio_loop]

        if not isinstance(
            asyncio_loop, getattr(asyncio, "ProactorEventLoop", type(None))
        ):
            return asyncio_loop

        warnings.warn(PROACTOR_WARNING, CurlCffiWarning, stacklevel=2)

        from ._asyncio_selector import AddThreadSelectorEventLoop

        selector_loop = _selectors[asyncio_loop] = AddThreadSelectorEventLoop(
            asyncio_loop
        )  # type: ignore

        # patch loop.close to also close the selector thread
        loop_close = asyncio_loop.close

        def _close_selector_and_loop():
            # restore original before calling selector.close,
            # which in turn calls eventloop.close!
            asyncio_loop.close = loop_close
            _selectors.pop(asyncio_loop, None)
            selector_loop.close()

        asyncio_loop.close = _close_selector_and_loop
        return selector_loop

else:

    def get_selector(loop: asyncio.AbstractEventLoop) -> asyncio.AbstractEventLoop:
        return loop



CURLPIPE_NOTHING = 0
CURLPIPE_HTTP1 = 1  # deprecated
CURLPIPE_MULTIPLEX = 2


class AsyncCurl(BaseAsyncCurl):
    """Wrapper around curl_multi handle to provide asyncio support. It uses the libcurl
    socket_action APIs."""

    def __init__(self, cacert: str = "", loop=None):
        """
        Args:
            cacert: CA cert path to use, by default, certs from ``certifi`` are used.
            loop: EventLoop to use.
        """
        self.loop = get_selector(
            loop if loop is not None else asyncio.get_running_loop()
        )
        super().__init__(cacert=cacert, cancelled_errors=(asyncio.CancelledError,))

    def create_task(self, coro):
        return self.loop.create_task(coro)

    def create_future(self):
        return self.loop.create_future()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
