# Simple smoke test to real world websites
from curl_cffi import requests

URLS = [
    "https://www.baidu.com",
    "https://www.qq.com",
]


def test_without_impersonate():
    for url in URLS:
        r = requests.get(url)
        assert r.status_code == 200


def test_with_impersonate():
    for url in URLS:
        r = requests.get(url, impersonate="chrome")
        assert r.status_code == 200


async def test_async():
    async with requests.AsyncSession() as s:
        for url in URLS:
            r = await s.get(url)
            assert r.status_code == 200
