import json
import os

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
    FingerprintManager.update_fingerprints()
    fingerprints = FingerprintManager.load_fingerprints()
    assert len(fingerprints) > 1
    for key in fingerprints:
        assert key.startswith("testing")


def test_single_fingerprint(mock_profiles_api):
    FingerprintManager.update_fingerprints("https://api.test")
    fingerprints = FingerprintManager.load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"


@pytest.mark.skip()
def test_using_profile():
    FingerprintManager.update_fingerprints("https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
