import os
import pytest
import curl_cffi
from curl_cffi.pro import (
    update_profiles,
    update_market_share,
    load_profiles,
    load_market_share,
    get_config_path,
    get_profile_path,
)


TESTING_API_KEY = "imp_alizee-lyonnet"



@pytest.fixture(scope="session", autouse=True)
def setup_pro():
    # login before testing starts
    curl_cffi.enable_pro(api_key=TESTING_API_KEY)
    yield
    # clean up after testing
    os.remove(get_config_path())
    os.remove(get_profile_path())


def test_is_pro():
    assert curl_cffi.is_pro() is True


def test_update_profiles(api_server):
    update_profiles(api_server.url)
    profiles = load_profiles()
    assert len(profiles) > 1
    for key in profiles:
        assert key.startswith("testing")


def test_single_profile(api_server):
    update_profiles(api_server.url)
    profiles = load_profiles()
    testing100 = profiles["testing100"]
    assert testing100.http2_settings == ""


@pytest.mark.skip()
def test_using_profile(api_server):
    update_profiles(api_server.url)
    curl_cffi.get("https://www.google.com", impersonate="testing1024")


@pytest.mark.skip()
def test_update_market_share(api_server):
    curl_cffi.get("https://www.google.com", impersonate="testing1024")
    update_market_share(api_root=api_server.url)
    market_share = load_market_share()
    curl_cffi.get("https://www.google.com", impersonate="real_world")
