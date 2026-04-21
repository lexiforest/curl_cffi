import os
from urllib.error import URLError

import pytest

from curl_cffi.fingerprints import FingerprintManager


TESTING_API_KEY = "imp_alizee-lyonnet"


@pytest.fixture(scope="session", autouse=True)
def setup_pro(tmp_path_factory):
    os.environ["IMPERSONATE_CONFIG_DIR"] = str(
        tmp_path_factory.mktemp("impersonate-pro-tests")
    )
    # login before testing starts
    FingerprintManager.set_api_key(api_key=TESTING_API_KEY)
    yield


def test_update_fingerprints(api_server):
    updated = FingerprintManager.update_fingerprints(api_server.url)
    fingerprints = FingerprintManager.load_fingerprints()
    assert updated == 10
    assert "testing100" in fingerprints
    assert "testing101" in fingerprints


def test_single_fingerprint(api_server):
    FingerprintManager.update_fingerprints(api_server.url)
    fingerprints = FingerprintManager.load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"
    assert testing100.http2_pseudo_headers_order == "masp"
    assert testing100.tls_supported_groups == ["X25519", "P-256", "P-384", "P-521"]


def test_update_fingerprints_prints_access_error(monkeypatch, capsys):
    def dummy_urlopen(request):
        raise URLError("Connection refused")

    monkeypatch.setattr("curl_cffi.fingerprints.urlopen", dummy_urlopen)

    updated = FingerprintManager.update_fingerprints("https://api.test")

    captured = capsys.readouterr()
    assert updated is None
    assert "updating fingerprints from https://api.test/fingerprints" in captured.out
    assert (
        "Failed to access fingerprint endpoint at "
        "https://api.test/fingerprints: <urlopen error Connection refused>"
        in captured.out
    )
