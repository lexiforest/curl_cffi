from curl_cffi import AsyncCurl, Curl


async def test_init(server):
    ac = AsyncCurl()


async def test_add_handle(server):
    ac = AsyncCurl()
    c = Curl()
    await ac.add_handle(c, wait=False)


async def test_socket_action(server):
    ac = AsyncCurl()
    running = ac.socket_action(-1, 0)
    # assert running == 0
    c = Curl()
    await ac.add_handle(c, wait=False)
    running = ac.socket_action(-1, 0)
    # assert running == 1


async def test_process_data(server):
    ...


