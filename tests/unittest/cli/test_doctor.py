import subprocess
import sys


def _run_cli(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "curl_cffi"] + list(args),
        capture_output=True,
        text=True,
        timeout=30,
        **kwargs,
    )


def test_cli_doctor():
    r = _run_cli("doctor")
    assert r.returncode == 0
    assert "curl-cffi doctor" in r.stdout
    assert "python:" in r.stdout
    assert "curl_cffi:" in r.stdout
    assert "libcurl:" in r.stdout
    assert "platform:" in r.stdout
    assert "machine:" in r.stdout
