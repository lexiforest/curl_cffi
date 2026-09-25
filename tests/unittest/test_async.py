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


async def test_multi_error_message_carries_the_libcurl_text():
    ac = AsyncCurl()
    with pytest.raises(CurlError, match=r"multi: \(1\) Invalid multi handle\. "):
        ac._check_error(1, "perform")
    await ac.close()
