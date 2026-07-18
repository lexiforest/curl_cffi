import pytest

from curl_cffi import AsyncCurl, Curl, CurlError, CurlOpt


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


async def test_close_ignores_already_closed_curl():
    ac = AsyncCurl()
    c = Curl()
    c.setopt(CurlOpt.URL, "http://example.com")
    future = ac.add_handle(c)

    future.cancel()
    c.close()

    await ac.close()

    assert not ac._curl2future
    assert not ac._curl2curl


async def test_remove_handle_error_cleans_up_closed_curl(monkeypatch):
    ac = AsyncCurl()
    c = Curl()
    c.setopt(CurlOpt.URL, "http://example.com")
    future = ac.add_handle(c)

    def raise_remove_error(*args):
        raise CurlError("remove failed")

    monkeypatch.setattr(ac, "_check_error", raise_remove_error)

    with pytest.raises(CurlError, match="remove failed"):
        ac.remove_handle(c)

    assert future.cancelled()
    assert c not in ac._curl2future
    assert c._curl not in ac._curl2curl

    c.close()
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
