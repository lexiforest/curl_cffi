from curl_cffi.requests import Headers


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
