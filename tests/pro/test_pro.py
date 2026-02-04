import json
import os

import pytest

import curl_cffi
import curl_cffi.pro as pro_module
from curl_cffi.pro import (
    load_market_share,
    load_profiles,
    update_market_share,
    update_profiles,
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

    monkeypatch.setattr(pro_module.requests, "get", fake_get)


def test_is_pro():
    assert curl_cffi.is_pro() is True


def test_update_profiles(mock_profiles_api):
    os.environ["IMPERSONATE_API_ROOT"] = "https://api.test"
    update_profiles()
    profiles = load_profiles()
    assert len(profiles) > 1
    for key in profiles:
        assert key.startswith("testing")


def test_single_profile(mock_profiles_api):
    update_profiles("https://api.test")
    profiles = load_profiles()
    testing100 = profiles["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"


@pytest.mark.skip()
def test_using_profile():
    update_profiles("https://api.test")
    curl_cffi.get("https://www.google.com", impersonate="testing1024")


@pytest.mark.skip()
def test_update_market_share():
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
    update_market_share(api_root="https://api.test")
    market_share = load_market_share()
    curl_cffi.get("https://www.google.com", impersonate="real_world")
