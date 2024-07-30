import pytest

from curl_cffi import requests

JA3_URL = "https://tls.browserleaks.com/json"
# Copied from my browser on macOS
CHROME_JA3_HASH = "53ff64ddf993ca882b70e1c82af5da49"
# Edge 101 is the same as Chrome 101
EDGE_JA3_HASH = "53ff64ddf993ca882b70e1c82af5da49"
# Same as safari 16.x
SAFARI_JA3_HASH = "8468a1ef6cb71b13e1eef8eadf786f7d"


def test_not_impersonate():
    r = requests.get(JA3_URL)
    assert r.json()["ja3_hash"] != CHROME_JA3_HASH


def test_impersonate():
    r = requests.get(JA3_URL, impersonate="chrome101")
    assert r.json()["ja3_hash"] == CHROME_JA3_HASH


def test_impersonate_edge():
    r = requests.get(JA3_URL, impersonate="edge101")
    assert r.json()["ja3_hash"] == EDGE_JA3_HASH


def test_impersonate_safari():
    r = requests.get(JA3_URL, impersonate="safari15_5")
    assert r.json()["ja3_hash"] == SAFARI_JA3_HASH


def test_impersonate_unknown():
    with pytest.raises(requests.RequestsError, match="not supported"):
        requests.get(JA3_URL, impersonate="unknown")
