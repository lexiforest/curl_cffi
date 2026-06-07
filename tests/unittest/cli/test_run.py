import json
import subprocess
import sys

from curl_cffi.cli import parse_http_file


def _run_cli(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "curl_cffi"] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Unit tests: parse_http_file
# ---------------------------------------------------------------------------


def test_parse_simple_get():
    requests = parse_http_file("GET http://example.com\n")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url == "http://example.com"


def test_parse_implicit_get():
    requests = parse_http_file("http://example.com\n")
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url == "http://example.com"


def test_parse_with_headers():
    text = "GET http://example.com\nAccept: application/json\nX-Custom: value\n"
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].headers == {"Accept": "application/json", "X-Custom": "value"}


def test_parse_with_body():
    text = (
        "POST http://example.com/api\n"
        "Content-Type: application/json\n"
        "\n"
        '{"key": "value"}\n'
    )
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].method == "POST"
    assert requests[0].body == '{"key": "value"}'


def test_parse_separator():
    text = "GET http://example.com/first\n###\nGET http://example.com/second\n"
    requests = parse_http_file(text)
    assert len(requests) == 2
    assert requests[0].url == "http://example.com/first"
    assert requests[1].url == "http://example.com/second"


def test_parse_separator_with_comment():
    text = (
        "GET http://example.com/first\n"
        "### this is a separator comment\n"
        "GET http://example.com/second\n"
    )
    requests = parse_http_file(text)
    assert len(requests) == 2


def test_parse_comments_skipped():
    text = "# comment before\n// another comment\nGET http://example.com\n"
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].url == "http://example.com"


def test_parse_http_version_ignored():
    text = "GET http://example.com HTTP/1.1\n"
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url == "http://example.com"


def test_parse_multiline_body():
    text = (
        "POST http://example.com\n"
        "Content-Type: text/plain\n"
        "\n"
        "line one\n"
        "line two\n"
        "line three\n"
    )
    requests = parse_http_file(text)
    assert requests[0].body == "line one\nline two\nline three"


def test_parse_empty_blocks_skipped():
    text = "###\n###\nGET http://example.com\n###\n"
    requests = parse_http_file(text)
    assert len(requests) == 1


def test_parse_multiple_requests_with_bodies():
    text = (
        "POST http://example.com/a\n"
        "Content-Type: application/json\n"
        "\n"
        '{"a": 1}\n'
        "###\n"
        "POST http://example.com/b\n"
        "Content-Type: application/json\n"
        "\n"
        '{"b": 2}\n'
    )
    requests = parse_http_file(text)
    assert len(requests) == 2
    assert requests[0].body == '{"a": 1}'
    assert requests[1].body == '{"b": 2}'


def test_parse_response_handler_ignored():
    text = (
        "GET http://example.com\n"
        "\n"
        '> {% client.global.set("auth", response.body.token); %}\n'
    )
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].body == ""


def test_parse_response_ref_ignored():
    text = "GET http://example.com\n\n<> previous-response.200.json\n"
    requests = parse_http_file(text)
    assert len(requests) == 1
    assert requests[0].body == ""


# ---------------------------------------------------------------------------
# Integration tests: run with .http files
# ---------------------------------------------------------------------------


def test_run_http_simple_get(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(f"GET {server.url}\n")
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_run_http_multiple_requests(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(f"GET {server.url}\n###\nGET {server.url}echo_params?foo=bar\n")
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_run_http_post_with_json_body(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(
        f"POST {server.url}echo_body\n"
        "Content-Type: application/json\n"
        "\n"
        '{"name": "alice"}\n'
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "alice" in r.stdout


def test_run_http_with_headers(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(f"GET {server.url}echo_headers\nX-Custom: myvalue\n")
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "myvalue" in r.stdout


def test_run_http_comments_and_blanks(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(f"# this is a comment\n// another comment\n\nGET {server.url}\n")
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_run_missing_file():
    r = _run_cli("run", "/nonexistent/file.http")
    assert r.returncode == 1
    assert "not found" in r.stderr


def test_run_http_reports_failures(server, tmp_path):
    f = tmp_path / "requests.http"
    f.write_text(f"GET {server.url}status/404\n###\nGET {server.url}\n")
    r = _run_cli("run", str(f))
    assert r.returncode == 1
    assert "1 request(s) failed" in r.stderr


def test_run_http_file_reference(server, tmp_path):
    body_file = tmp_path / "body.json"
    body_file.write_text('{"name": "fromfile"}')
    f = tmp_path / "requests.http"
    f.write_text(
        f"POST {server.url}echo_body\nContent-Type: application/json\n\n< {body_file}\n"
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "fromfile" in r.stdout


# ---------------------------------------------------------------------------
# Integration tests: run with .har files
# ---------------------------------------------------------------------------


def _make_har(entries):
    """Build a minimal HAR structure."""
    return json.dumps({"log": {"entries": entries}})


def test_run_har_get(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {"request": {"method": "GET", "url": str(server.url)}},
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_run_har_multiple_entries(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {"request": {"method": "GET", "url": str(server.url)}},
                {"request": {"method": "GET", "url": f"{server.url}echo_params?x=1"}},
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "Hello, world!" in r.stdout


def test_run_har_post_json(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {
                    "request": {
                        "method": "POST",
                        "url": f"{server.url}echo_body",
                        "headers": [
                            {"name": "Content-Type", "value": "application/json"}
                        ],
                        "postData": {
                            "mimeType": "application/json",
                            "text": '{"name": "bob"}',
                        },
                    }
                },
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "bob" in r.stdout


def test_run_har_post_form(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {
                    "request": {
                        "method": "POST",
                        "url": f"{server.url}echo_body",
                        "headers": [
                            {
                                "name": "Content-Type",
                                "value": "application/x-www-form-urlencoded",
                            }
                        ],
                        "postData": {
                            "mimeType": "application/x-www-form-urlencoded",
                            "text": "key=val",
                        },
                    }
                },
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "key" in r.stdout


def test_run_har_with_headers(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {
                    "request": {
                        "method": "GET",
                        "url": f"{server.url}echo_headers",
                        "headers": [
                            {"name": "X-Custom", "value": "harvalue"},
                            {"name": "Host", "value": "should-be-skipped"},
                        ],
                    }
                },
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 0
    assert "harvalue" in r.stdout


def test_run_har_missing_file():
    r = _run_cli("run", "/nonexistent/test.har")
    assert r.returncode == 1
    assert "not found" in r.stderr


def test_run_har_invalid_json(tmp_path):
    f = tmp_path / "bad.har"
    f.write_text("{not valid json")
    r = _run_cli("run", str(f))
    assert r.returncode == 1
    assert "invalid HAR JSON" in r.stderr


def test_run_har_empty_entries(tmp_path):
    f = tmp_path / "empty.har"
    f.write_text(_make_har([]))
    r = _run_cli("run", str(f))
    assert r.returncode == 1
    assert "no entries" in r.stderr


def test_run_unsupported_format(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    r = _run_cli("run", str(f))
    assert r.returncode == 1
    assert "unsupported file format" in r.stderr


def test_run_har_reports_failures(server, tmp_path):
    f = tmp_path / "test.har"
    f.write_text(
        _make_har(
            [
                {"request": {"method": "GET", "url": f"{server.url}status/500"}},
                {"request": {"method": "GET", "url": str(server.url)}},
            ]
        )
    )
    r = _run_cli("run", str(f))
    assert r.returncode == 1
    assert "1 request(s) failed" in r.stderr
