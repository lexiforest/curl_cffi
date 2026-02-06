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
        def json(self):
            return payload

    class DummyRequests:
        @staticmethod
        def get(url, cookies=None):
            assert url.endswith("/fingerprints")
            return DummyResponse()

    monkeypatch.setattr(
        FingerprintManager,
        "_get_requests_module",
        staticmethod(lambda: DummyRequests()),
    )


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


@pytest.mark.skip()
def test_update_market_share():
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
    FingerprintManager.update_market_share(api_root="https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="real_world")
