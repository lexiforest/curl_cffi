from unittest.mock import Mock

import pytest

from curl_cffi import AsyncCurl, Curl, CurlOpt
from curl_cffi.async_base import timer_function

pytestmark = pytest.mark.asyncio


async def test_init(server):
    ac = AsyncCurl()  # noqa F841


async def test_add_handle(server):
    ac = AsyncCurl()
    c = Curl()
    c.setopt(CurlOpt.URL, str(server.url))
    c.setopt(CurlOpt.WRITEFUNCTION, lambda x: len(x))
    fut = ac.add_handle(c)
    await fut


async def test_add_handle_callback_exception(server):
    ac = AsyncCurl()
    c = Curl()
    c.setopt(CurlOpt.URL, str(server.url).encode())

    def write(data: bytes):
        raise ValueError("callback failed")

    c.setopt(CurlOpt.WRITEFUNCTION, write)
    with pytest.raises(ValueError, match="callback failed"):
        await ac.add_handle(c)
    await ac.close()


async def test_socket_action(server):
    ac = AsyncCurl()
    running = ac.socket_action(-1, 0)
    # assert running == 0
    c = Curl()
    c.setopt(CurlOpt.URL, str(server.url))
    c.setopt(CurlOpt.WRITEFUNCTION, lambda x: len(x))
    fut = ac.add_handle(c)
    await fut
    running = ac.socket_action(-1, 0)  # noqa F841
    # assert running == 1


async def test_process_data(server): ...


async def test_timer_cancellation():
    ac = AsyncCurl()
    timer = ac.loop.call_later(60, lambda: None)
    ac._timer = timer
    try:
        assert timer_function(None, -1, ac._self_handle) == 0
        assert timer.cancelled()
        assert ac._timer is None
    finally:
        await ac.close()


async def test_force_timeout_processes_completions():
    ac = AsyncCurl()
    process_data = Mock(side_effect=lambda *_: setattr(ac, "_curlm", None))
    curlm = ac._curlm
    ac.process_data = process_data
    try:
        await ac._timeout_checker
        process_data.assert_called_once_with(-1, 0)
    finally:
        ac._curlm = curlm
        await ac.close()
