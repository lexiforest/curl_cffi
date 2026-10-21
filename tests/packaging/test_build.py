import platform
import re
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, Mock

import pytest


@pytest.mark.parametrize("link_type", ["static", "dynamic"])
def test_macos_link_args(monkeypatch, tmp_path, link_type):
    monkeypatch.setenv("IMPERSONATE_BUILD_DIR", str(tmp_path))
    monkeypatch.setenv("IMPERSONATE_LINK_TYPE", link_type)
    monkeypatch.setenv("CURL_CFFI_TARGET_MACHINE", "arm64")
    monkeypatch.setenv("CURL_CFFI_TARGET_POINTER_SIZE", "64")
    for name in ("CIBW_PLATFORM", "ANDROID_ROOT", "ANDROID_DATA", "TERMUX_VERSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        platform, "uname", lambda: SimpleNamespace(system="Darwin", machine="arm64")
    )
    suffix = "a" if link_type == "static" else "dylib"
    library = tmp_path / f"libcurl-impersonate.{suffix}"
    library.touch()
    if link_type == "static":
        (tmp_path / "libcurl-impersonate.pc").touch()

    ffi = Mock()
    monkeypatch.setitem(sys.modules, "cffi", SimpleNamespace(FFI=lambda: ffi))
    pkg_config = Mock(
        return_value="-lcurl-impersonate -lc++ "
        "-framework CoreFoundation -framework SystemConfiguration"
    )
    monkeypatch.setattr(subprocess, "check_output", pkg_config)

    runpy.run_path(str(Path(__file__).parents[2] / "scripts/build.py"))
    source = ffi.set_source.call_args.kwargs

    if link_type == "static":
        pkg_config.assert_called_once_with(
            ["pkg-config", "--static", "--libs", "libcurl-impersonate"],
            env=ANY,
            text=True,
        )
        assert source["libraries"] == []
        assert source["extra_link_args"] == [
            f"-Wl,-force_load,{library}",
            "-lc++",
            "-framework",
            "CoreFoundation",
            "-framework",
            "SystemConfiguration",
        ]
    else:
        pkg_config.assert_not_called()
        assert source["libraries"] == ["curl-impersonate"]
        assert source["extra_link_args"] == []


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS linker regression")
def test_system_framework_symbols_are_linked():
    from curl_cffi import _wrapper

    symbols = subprocess.check_output(["nm", "-m", "-u", _wrapper.__file__], text=True)
    unresolved = [
        line
        for line in symbols.splitlines()
        if re.search(r"external _(?:CF|SC|kCF)", line)
        and "dynamically looked up" in line
    ]
    assert not unresolved, "Unlinked system framework symbols:\n" + "\n".join(
        unresolved
    )
