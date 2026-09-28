import subprocess
import sys


def test_transfer_in_fresh_interpreter(tmp_path):
    # Test an installed wheel without source-tree imports or prior dlopen calls.
    source = tmp_path / "response.txt"
    payload = b"curl_cffi fresh interpreter transfer\n"
    source.write_bytes(payload)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            """
import sys
from io import BytesIO
from curl_cffi import Curl, CurlOpt

body = BytesIO()
curl = Curl()
try:
    curl.setopt(CurlOpt.URL, sys.argv[1].encode())
    curl.setopt(CurlOpt.WRITEDATA, body)
    curl.perform()
finally:
    curl.close()
sys.stdout.buffer.write(body.getvalue())
""",
            source.as_uri(),
        ],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    assert result.stdout == payload
