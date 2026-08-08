import pytest

from curl_cffi.const import CurlOpt
from curl_cffi.requests import AsyncSession, Session


def test_dns_string_is_stored_in_curl_options():
    s = Session(dns="114.114.114.114")
    assert s.curl_options[CurlOpt.DNS_SERVERS] == "114.114.114.114"


def test_dns_list_is_joined_with_comma():
    s = Session(dns=["114.114.114.114", "8.8.8.8"])
    assert s.curl_options[CurlOpt.DNS_SERVERS] == "114.114.114.114,8.8.8.8"


def test_dns_empty_list_is_ignored():
    s = Session(dns=[])
    assert CurlOpt.DNS_SERVERS not in s.curl_options


def test_dns_empty_string_is_ignored():
    s = Session(dns="")
    assert CurlOpt.DNS_SERVERS not in s.curl_options


def test_dns_tuple_is_joined_with_comma():
    s = Session(dns=("114.114.114.114", "8.8.8.8"))
    assert s.curl_options[CurlOpt.DNS_SERVERS] == "114.114.114.114,8.8.8.8"


def test_dns_invalid_type_raises_type_error():
    with pytest.raises(TypeError):
        Session(dns=42.42)


def test_async_session_dns_string_is_stored_in_curl_options():
    a = AsyncSession(dns="114.114.114.114")
    assert a.curl_options[CurlOpt.DNS_SERVERS] == "114.114.114.114"
