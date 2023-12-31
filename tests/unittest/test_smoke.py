# Simple smoke test to real world websites
from curl_cffi import requests


URLS = [
    "https://www.zhihu.com",
    "https://www.weibo.com",
]


def test_without_impersonate():
    for url in URLS:
        r = requests.get(url)
        assert r.status_code == 200


def test_with_impersonate():
    for url in URLS:
        r = requests.get(url, impersonate=requests.BrowserType.chrome)
        assert r.status_code == 200
