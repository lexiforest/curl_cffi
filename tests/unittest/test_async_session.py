from curl_cffi.requests import AsyncSession


async def test_get(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url))
        assert r.status_code == 200
