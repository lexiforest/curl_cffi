import pytest
from curl_cffi import requests


#######################################################################################
# testing httpbin
#######################################################################################


def test_gzip():
    r = requests.get("https://httpbin.org/gzip")
    assert r.status_code == 200
    assert r.json()["gzipped"]


def test_brotli():
    r = requests.get("https://httpbin.org/brotli")
    assert r.status_code == 200
    assert r.json()["brotli"]


def test_redirect_n():
    r = requests.get("https://httpbin.org/absolute-redirect/3")
    assert r.status_code == 200


def test_relative_redirect_n():
    r = requests.get("https://httpbin.org/relative-redirect/3")
    assert r.status_code == 200


def test_redirect_max():
    with pytest.raises(requests.RequestsError, match="Failed"):
        requests.get("https://httpbin.org/redirect/5", max_redirects=3)


def test_imperonsate_default_headers():
    r = requests.get("http://postman-echo.com/headers", impersonate="chrome110")
    headers = r.json()
    assert "Mozilla" in headers["headers"]["user-agent"]
    r = requests.get(
        "http://httpbin.org/headers",
        impersonate="chrome110",
        default_headers=False,
    )
    headers = r.json()
    assert "user-agent" not in headers["headers"]
