from curl_cffi.requests import Headers
from curl_cffi.requests.session import _update_header_line


def test_headers():
    headers = Headers()
    headers["foo"] = "bar"
    headers["foo"] = "baz"
    assert headers["foo"] == "baz"
    assert headers.get("foo") == "baz"
    assert headers.get("bar") is None
    assert headers


def test_headers_none_value():
    headers = Headers({"foo": None, "bar": ""})
    assert headers.get("foo") is None
    assert headers["bar"] == ""


def test_header_output():
    headers = Headers({"X-Foo": "bar"})
    header_list = headers.multi_items()
    assert header_list[0][0] == "X-Foo"


def test_replace_header():
    header_lines = []
    _update_header_line(header_lines, "content-type", "image/png")
    assert header_lines == ["content-type: image/png"]
    _update_header_line(header_lines, "Content-Type", "application/json")
    assert header_lines == ["content-type: image/png"]
    _update_header_line(header_lines, "Content-Type", "application/json", replace=True)
    assert header_lines == ["Content-Type: application/json"]
    _update_header_line(header_lines, "Host", "example.com", replace=True)
    assert header_lines == ["Content-Type: application/json", "Host: example.com"]
