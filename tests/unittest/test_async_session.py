from curl_cffi.requests import AsyncSession


async def test_get(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url))
        assert r.status_code == 200


async def test_post_dict(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b"foo=bar"


async def test_post_str(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}')
        assert r.status_code == 200
        assert r.content == b'{"foo": "bar"}'


async def test_post_json(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b'{"foo": "bar"}'
