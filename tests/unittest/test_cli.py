import subprocess


def test_cli(server):
    """Test that the curl-cffi CLI can perform basic GET requests."""
    result = subprocess.check_output(
        f"curl-cffi {server.url}",
        shell=True,
        text=True,
        timeout=30,
    )
    # Should look like HTTP response:
    assert "Hello, world!" in result
