import json
import subprocess
import sys

import pytest

from curl_cffi.cli import extract_positionals, parse_request_items, process_url


# ---------------------------------------------------------------------------
# Unit tests: process_url
# ---------------------------------------------------------------------------


def test_process_url_localhost_shortcut():
    assert process_url(":3000") == "http://localhost:3000"


def test_process_url_localhost_shortcut_with_path():
    assert process_url(":8080/api") == "http://localhost:8080/api"


def test_process_url_default_scheme():
    assert process_url("example.com") == "https://example.com"


def test_process_url_preserves_https():
    assert process_url("https://example.com") == "https://example.com"


def test_process_url_preserves_http():
    assert process_url("http://example.com") == "http://example.com"


# ---------------------------------------------------------------------------
# Unit tests: parse_request_items
# ---------------------------------------------------------------------------


def test_parse_header():
    result = parse_request_items(["Content-Type:application/json"])
    assert result.headers == {"Content-Type": "application/json"}


def test_parse_header_with_colon_in_value():
    result = parse_request_items(["Authorization:Bearer token123"])
    assert result.headers == {"Authorization": "Bearer token123"}


def test_parse_header_removal():
    result = parse_request_items(["Accept:"])
    assert result.headers_to_remove == ["Accept"]


def test_parse_query_param():
    result = parse_request_items(["page==2"])
    assert result.query_params == [("page", "2")]


def test_parse_data_field():
    result = parse_request_items(["name=John"])
    assert result.data_fields == [("name", "John")]


def test_parse_data_field_with_equals_in_value():
    result = parse_request_items(["formula=a=b"])
    assert result.data_fields == [("formula", "a=b")]


def test_parse_json_field_number():
    result = parse_request_items(["count:=42"])
    assert result.json_fields == [("count", 42)]


def test_parse_json_field_bool():
    result = parse_request_items(["active:=true"])
    assert result.json_fields == [("active", True)]


def test_parse_json_field_object():
    result = parse_request_items(['config:={"key":"val"}'])
    assert result.json_fields == [("config", {"key": "val"})]


def test_parse_file_upload():
    result = parse_request_items(["@/path/to/file.txt"])
    assert result.files == [("file", "/path/to/file.txt")]


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


def test_parse_invalid_json_exits():
    with pytest.raises(SystemExit):
        parse_request_items(["bad:={invalid}"])


def test_parse_unknown_item_exits():
    with pytest.raises(SystemExit):
        parse_request_items(["notseparated"])


# ---------------------------------------------------------------------------
# Unit tests: extract_positionals
# ---------------------------------------------------------------------------


def test_extract_method_and_url():
    method, url, items = extract_positionals(["GET", "http://example.com"])
    assert method == "GET"
    assert url == "http://example.com"
    assert items == []


def test_extract_url_only():
    method, url, items = extract_positionals(["http://example.com"])
    assert method is None
    assert url == "http://example.com"
    assert items == []


def test_extract_method_url_and_items():
    method, url, items = extract_positionals(
        [
            "POST",
            "http://example.com",
            "name=test",
            "X-Foo:bar",
        ]
    )
    assert method == "POST"
    assert url == "http://example.com"
    assert items == ["name=test", "X-Foo:bar"]


def test_extract_case_insensitive_method():
    method, url, _ = extract_positionals(["post", "http://example.com"])
    assert method == "POST"


def test_extract_no_args_exits():
    with pytest.raises(SystemExit):
        extract_positionals([])


def test_extract_method_only_exits():
    with pytest.raises(SystemExit):
        extract_positionals(["GET"])


# ---------------------------------------------------------------------------
# Integration tests (using the test server)
# ---------------------------------------------------------------------------


def _run_cli(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "curl_cffi"] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


def test_cli_get_default(server):
    r = _run_cli(str(server.url))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_cli_explicit_get(server):
    r = _run_cli("GET", str(server.url))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_cli_post_json(server):
    r = _run_cli("POST", f"{server.url}echo_body", "name=test")
    assert r.returncode == 0
    body = json.loads(r.stdout.split("\n\n")[-1].strip())
    assert body["name"] == "test"


def test_cli_headers(server):
    r = _run_cli(f"{server.url}echo_headers", "X-Custom:myvalue")
    assert r.returncode == 0
    assert "myvalue" in r.stdout


def test_cli_query_params(server):
    r = _run_cli(f"{server.url}echo_params", "foo==bar")
    assert r.returncode == 0
    assert "bar" in r.stdout


def test_cli_verbose(server):
    r = _run_cli("-v", str(server.url))
    assert r.returncode == 0
    assert "GET" in r.stdout
    assert "200" in r.stdout


def test_cli_body_only(server):
    r = _run_cli("--body", str(server.url))
    assert r.returncode == 0
    assert "HTTP/" not in r.stdout
    assert "Hello, world!" in r.stdout


def test_cli_impersonate(server):
    r = _run_cli("-i", "chrome", str(server.url))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_cli_doctor():
    r = _run_cli("doctor")
    assert r.returncode == 0
    assert "curl-cffi doctor" in r.stdout
    assert "python:" in r.stdout
    assert "curl_cffi:" in r.stdout
    assert "libcurl:" in r.stdout
