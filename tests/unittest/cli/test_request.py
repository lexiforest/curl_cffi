import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import curl_cffi


def _run_cli(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "curl_cffi"] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


@pytest.mark.parametrize(
    "args_fn, expected_in_stdout",
    [
        (lambda url: ["get", url], "Hello, world!"),
        (lambda url: ["GET", url], "Hello, world!"),
        (lambda url: ["get", "-i", "chrome", url], "Hello, world!"),
        (lambda url: ["get", f"{url}echo_headers", "X-Custom:myvalue"], "myvalue"),
        (lambda url: ["get", f"{url}echo_params", "foo==bar"], "bar"),
    ],
)
def test_cli_basic(server, args_fn, expected_in_stdout):
    r = _run_cli(*args_fn(str(server.url)))
    assert r.returncode == 0
    assert expected_in_stdout in r.stdout


@pytest.mark.parametrize(
    "args_fn, expected_in_stdout",
    [
        (lambda url: ["POST", f"{url}echo_body", "name=test"], "test"),
        (lambda url: ["post", f"{url}echo_body", "name=test"], "test"),
    ],
)
def test_cli_post(server, args_fn, expected_in_stdout):
    r = _run_cli(*args_fn(str(server.url)))
    assert r.returncode == 0
    assert expected_in_stdout in r.stdout


def test_cli_post_json(server):
    r = _run_cli("post", f"{server.url}echo_body", "name=test")
    assert r.returncode == 0
    body = json.loads(r.stdout.split("\n\n")[-1].strip())
    assert body["name"] == "test"


def test_cli_get_verbose(server):
    r = _run_cli("get", "-v", str(server.url))
    assert r.returncode == 0
    assert "GET" in r.stdout
    assert "200" in r.stdout


def test_cli_get_body_only(server):
    r = _run_cli("get", "--body", str(server.url))
    assert r.returncode == 0
    assert "HTTP/" not in r.stdout
    assert "Hello, world!" in r.stdout


def test_cli_get_quiet(server):
    r = _run_cli("get", "--quiet", str(server.url))
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""


def test_cli_download_quiet(server, tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(curl_cffi.__file__).parent.parent)
    r = _run_cli(
        "get",
        "-q",
        "-d",
        "-o",
        "response.txt",
        str(server.url),
        cwd=tmp_path,
        env=env,
    )
    assert r.returncode == 0
    assert r.stdout == ""
    assert r.stderr == ""
    assert (tmp_path / "response.txt").read_text() == "Hello, world!"


def test_cli_no_args_shows_help():
    r = _run_cli()
    assert r.returncode == 0
    assert "curl-cffi" in r.stdout
