import asyncio

import pytest

from curl_cffi import AsyncCurl, Curl, CurlOpt


async def test_init(server):
    ac = AsyncCurl()  # noqa F841


async def test_add_handle(server):
    ac = AsyncCurl()
    c = Curl()
    c.setopt(CurlOpt.URL, "http://example.com")
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
    c.setopt(CurlOpt.URL, "http://example.com")
    c.setopt(CurlOpt.WRITEFUNCTION, lambda x: len(x))
    fut = ac.add_handle(c)
    await fut
    running = ac.socket_action(-1, 0)  # noqa F841
    # assert running == 1


async def test_process_data(server): ...


async def test_force_timeout_error():
    """socket_action errors should not kill the _force_timeout safeguard."""
    ac = AsyncCurl()

    calls = {"n": 0, "raised": False}
    real_socket_action = ac.socket_action

    def flaky_socket_action(sockfd, ev_bitmask):
        if not calls["raised"]:
            calls["raised"] = True
            raise RuntimeError("transient socket_action error")
        calls["n"] += 1
        return real_socket_action(sockfd, ev_bitmask)

    ac.socket_action = flaky_socket_action

    # raise once, then keep ticking if the safeguard survived
    await asyncio.sleep(0.35)

    assert calls["raised"]
    assert not ac._timeout_checker.done()
    assert calls["n"] >= 1

    await ac.close()
