import platform
import subprocess

import pytest


@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS-only test")
def test_wrapper_links_macos_system_frameworks():
    from curl_cffi import _wrapper

    dependencies = subprocess.run(
        ["otool", "-L", _wrapper.__file__],
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    assert "CoreFoundation.framework" in dependencies
    assert "SystemConfiguration.framework" in dependencies
