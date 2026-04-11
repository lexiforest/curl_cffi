from argparse import Namespace

from curl_cffi.cli.pro import handle_pro_command
from curl_cffi.fingerprints import FingerprintManager


def test_is_pro(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    FingerprintManager.is_pro.cache_clear()
    assert FingerprintManager.is_pro() is False


def test_handle_update_prints_cache_total(monkeypatch, capsys):
    monkeypatch.setattr(FingerprintManager, "update_fingerprints", lambda: 2)

    assert handle_pro_command(Namespace(command="update")) is True

    captured = capsys.readouterr()
    assert captured.out == "Total 2 fingerprints in cache.\n"
