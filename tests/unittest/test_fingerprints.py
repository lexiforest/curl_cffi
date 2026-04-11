import ntpath
import os

from curl_cffi.fingerprints import FingerprintManager, _get_default_config_dir


def test_get_default_config_dir_linux_xdg(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-config")

    assert _get_default_config_dir() == "/tmp/xdg-config/impersonate"


def test_get_default_config_dir_linux_fallback(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/tester")

    assert _get_default_config_dir() == "/home/tester/.config/impersonate"


def test_get_default_config_dir_macos(monkeypatch):
    monkeypatch.setattr(os, "name", "posix")
    monkeypatch.setenv("HOME", "/Users/tester")

    assert _get_default_config_dir() == "/Users/tester/.config/impersonate"


def test_get_default_config_dir_windows(monkeypatch):
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr("curl_cffi.fingerprints.os.path", ntpath)
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")

    assert (
        _get_default_config_dir() == r"C:\Users\tester\AppData\Roaming\impersonate"
    )


def test_get_config_dir_prefers_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    assert FingerprintManager.get_config_dir() == str(tmp_path)
