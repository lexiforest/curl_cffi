import pytest

from curl_cffi import requests
from curl_cffi.const import CurlHttpVersion


def test_impersonate_with_version(server):
    # the test server does not understand http/2
    r = requests.get(str(server.url), impersonate="chrome120", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200
    r = requests.get(str(server.url), impersonate="safari17_0", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200


def test_impersonate_without_version(server):
    r = requests.get(str(server.url), impersonate="chrome", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200
    r = requests.get(str(server.url), impersonate="safari_ios", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200


def test_impersonate_non_exist(server):
    with pytest.raises(requests.RequestsError, match="Impersonating"):
        requests.get(str(server.url), impersonate="edge")
    with pytest.raises(requests.RequestsError, match="Impersonating"):
        requests.get(str(server.url), impersonate="chrome2952")
