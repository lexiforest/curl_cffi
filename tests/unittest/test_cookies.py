import pytest
from curl_cffi.requests.cookies import Cookies
from curl_cffi.requests.errors import CookieConflict


def test_cookies_conflict():
    c = Cookies()
    c.set("foo", "bar", domain="example.com")
    c.set("foo", "baz", domain="test.local")
    with pytest.raises(CookieConflict):
        c.get("foo")


def test_cookies_conflict_on_subdomain():
    c = Cookies()
    c.set("foo", "bar", domain=".example.com")
    c.set("foo", "baz", domain="a.example.com")
    assert c.get("foo") in ("bar", "baz")


def test_cookies_conflict_but_same():
    c = Cookies()
    c = Cookies()
    c.set("foo", "bar", domain="example.com")
    c.set("foo", "bar", domain="test.local")
    assert c.get("foo") == "bar"
