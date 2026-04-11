import json
import os
from urllib.error import URLError

import pytest

import curl_cffi
from curl_cffi.fingerprints import FingerprintManager


TESTING_API_KEY = "imp_alizee-lyonnet"


def test_manager_enable_pro_and_is_pro(tmp_path, monkeypatch):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    FingerprintManager.enable_pro("imp_test")

    assert FingerprintManager.is_pro() is True


@pytest.fixture(scope="session", autouse=True)
def setup_pro(tmp_path_factory):
    os.environ["IMPERSONATE_CONFIG_DIR"] = str(
        tmp_path_factory.mktemp("impersonate-pro-tests")
    )
    # login before testing starts
    FingerprintManager.enable_pro(api_key=TESTING_API_KEY)
    yield


@pytest.fixture()
def mock_profiles_api(monkeypatch):
    payload = [
        {
            "name": "testing100",
            "data": json.dumps({"http2_settings": "1:65536;3:1000;4:6291456;6:262144"}),
        },
        {"name": "testing101", "data": json.dumps({"http2_settings": "1:1"})},
    ]

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode()

    def dummy_urlopen(request):
        assert request.full_url.endswith("/fingerprints")
        headers = dict(request.header_items())
        assert headers.get("Authorization") == f"Bearer {TESTING_API_KEY}"
        return DummyResponse()

    monkeypatch.setattr("curl_cffi.fingerprints.urlopen", dummy_urlopen)


def test_is_pro():
    assert FingerprintManager.is_pro() is True


def test_update_fingerprints(mock_profiles_api):
    os.environ["IMPERSONATE_API_ROOT"] = "https://api.test"
    updated = FingerprintManager.update_fingerprints()
    fingerprints = FingerprintManager.load_fingerprints()
    assert updated == 2
    assert "testing100" in fingerprints
    assert "testing101" in fingerprints


def test_single_fingerprint(mock_profiles_api):
    FingerprintManager.update_fingerprints("https://api.test")
    fingerprints = FingerprintManager.load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"


def test_update_fingerprints_new_api_shape(monkeypatch):
    payload = {
        "pagination": {
            "skip": 0,
            "limit": 100,
            "total": 1,
            "has_more": False,
            "next_skip": None,
        },
        "data": [
            {
                "name": "testing102",
                "fingerprint": {
                    "http2_settings": "1:65536;2:0;4:6291456;6:262144",
                    "http2_priority_weight": 256,
                    "http2_priority_exclusive": 1,
                },
            }
        ],
    }

    class DummyResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(payload).encode()

    def dummy_urlopen(request):
        assert request.full_url.endswith("/fingerprints")
        headers = dict(request.header_items())
        assert headers.get("Authorization") == f"Bearer {TESTING_API_KEY}"
        return DummyResponse()

    monkeypatch.setattr("curl_cffi.fingerprints.urlopen", dummy_urlopen)

    FingerprintManager.update_fingerprints("https://api.test")
    fingerprints = FingerprintManager.load_fingerprints()
    testing102 = fingerprints["testing102"]
    assert testing102.http2_settings == "1:65536;2:0;4:6291456;6:262144"
    assert testing102.http2_priority_weight == 256
    assert testing102.http2_priority_exclusive == 1


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


@pytest.mark.skip()
def test_using_profile():
    FingerprintManager.update_fingerprints("https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
