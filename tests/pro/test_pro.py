import json
import os

import pytest

import curl_cffi
import curl_cffi.fingerprints as fingerprints_module
from curl_cffi.fingerprints import (
    load_fingerprints,
    update_market_share,
    update_fingerprints,
)


TESTING_API_KEY = "imp_alizee-lyonnet"


@pytest.fixture(scope="session", autouse=True)
def setup_pro(tmp_path_factory):
    os.environ["IMPERSONATE_CONFIG_DIR"] = str(
        tmp_path_factory.mktemp("impersonate-pro-tests")
    )
    # login before testing starts
    curl_cffi.enable_pro(api_key=TESTING_API_KEY)
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

    def fake_get(url, cookies=None):
        assert url.endswith("/fingerprints")
        return DummyResponse()

    monkeypatch.setattr(fingerprints_module.requests, "get", fake_get)


def test_is_pro():
    assert curl_cffi.is_pro() is True


def test_update_fingerprints(mock_profiles_api):
    os.environ["IMPERSONATE_API_ROOT"] = "https://api.test"
    update_fingerprints()
    fingerprints = load_fingerprints()
    assert len(fingerprints) > 1
    for key in fingerprints:
        assert key.startswith("testing")


def test_single_fingerprint(mock_profiles_api):
    update_fingerprints("https://api.test")
    fingerprints = load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"


@pytest.mark.skip()
def test_using_profile():
    update_fingerprints("https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="testing1024")


@pytest.mark.skip()
def test_update_market_share():
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
    update_market_share(api_root="https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="real_world")
