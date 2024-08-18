import pytest

from curl_cffi.requests.cookies import Cookies, CurlMorsel
from curl_cffi.requests.errors import CookieConflict, RequestsError


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


def test_curl_format_with_hostname():
    m = CurlMorsel(name="foo", value="bar", hostname="example.com")
    assert m.to_curl_format() == "example.com\tFALSE\t/\tFALSE\t0\tfoo\tbar"
    m = CurlMorsel(name="foo", value="bar", hostname="example.com", secure=True)
    assert m.to_curl_format() == "example.com\tFALSE\t/\tTRUE\t0\tfoo\tbar"
    m = CurlMorsel(name="foo", value="bar", hostname="example.com", path="/path")
    assert m.to_curl_format() == "example.com\tFALSE\t/path\tFALSE\t0\tfoo\tbar"


def test_curl_format_without_hostname():
    m = CurlMorsel(name="foo", value="bar")
    with pytest.raises(RequestsError):
        m.to_curl_format()


def test_get_dict():
    c = Cookies({"foo": "bar"})
    d = c.get_dict()
    assert d == {"foo": "bar"}

    c = Cookies({"foo": "bar", "hello": "world", "a": "b"})
    d = c.get_dict()
    assert len(d) == 3
    assert d["foo"] == "bar"
    assert d["hello"] == "world"
    assert d["a"] == "b"

    c = Cookies()
    c.set("foo", "bar", domain="example.com")
    c.set("hello", "world", domain="example.com")
    c.set("foo", "bar", domain="test.local")
    d_example = c.get_dict("example.com")
    d_test = c.get_dict("test.local")
    assert len(d_example) == 2
    assert d_example["foo"] == "bar"
    assert d_example["hello"] == "world"
    assert len(d_test) == 1
    assert d_test["foo"] == "bar"
