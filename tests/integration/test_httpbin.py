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
        r = requests.get("https://httpbin.org/redirect/5", max_redirects=3)
