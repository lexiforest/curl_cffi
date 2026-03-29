import pytest

from curl_cffi.cli import parse_request_items, process_url


@pytest.mark.parametrize(
    "url, expected",
    [
        (":3000", "http://localhost:3000"),
        (":8080/api", "http://localhost:8080/api"),
        ("example.com", "https://example.com"),
        ("example.com:8080", "http://example.com:8080"),
        ("example.com:8080/api", "http://example.com:8080/api"),
        ("example.com:443", "https://example.com:443"),
        ("https://example.com", "https://example.com"),
        ("http://example.com", "http://example.com"),
    ],
)
def test_process_url(url, expected):
    assert process_url(url) == expected


@pytest.mark.parametrize(
    "items, field, expected",
    [
        (["Content-Type:application/json"], "headers", {"Content-Type": "application/json"}),
        (["Authorization:Bearer token123"], "headers", {"Authorization": "Bearer token123"}),
        (["Accept:"], "headers_to_remove", ["Accept"]),
        (["page==2"], "query_params", [("page", "2")]),
        (["name=John"], "data_fields", [("name", "John")]),
        (["formula=a=b"], "data_fields", [("formula", "a=b")]),
        (["count:=42"], "json_fields", [("count", 42)]),
        (["active:=true"], "json_fields", [("active", True)]),
        (['config:={"key":"val"}'], "json_fields", [("config", {"key": "val"})]),
        (["@/path/to/file.txt"], "files", [("file", "/path/to/file.txt")]),
        (["+session=abc123"], "cookies", {"session": "abc123"}),
        (["+session=abc", "+theme=dark"], "cookies", {"session": "abc", "theme": "dark"}),
    ],
)
def test_parse_request_items(items, field, expected):
    result = parse_request_items(items)
    assert getattr(result, field) == expected


def test_parse_multiple_items():
    result = parse_request_items(
        [
            "X-Custom:value",
            "q==search",
            "name=test",
            "count:=5",
        ]
    )
    assert result.headers == {"X-Custom": "value"}
    assert result.query_params == [("q", "search")]
    assert result.data_fields == [("name", "test")]
    assert result.json_fields == [("count", 5)]


@pytest.mark.parametrize(
    "items",
    [
        (["bad:={invalid}"]),
        (["notseparated"]),
    ],
)
def test_parse_request_items_exits_on_invalid(items):
    with pytest.raises(SystemExit):
        parse_request_items(items)
