from unittest.mock import Mock

from curl_cffi.const import CurlOpt
from curl_cffi.fingerprints import Fingerprint
from curl_cffi.requests.impersonate import ExtraFingerprints
from curl_cffi.requests.utils import _apply_fingerprint
from curl_cffi.requests.utils import set_extra_fp


class FakeCurl:
    def __init__(self):
        self.options = {}

    def setopt(self, option, value):
        self.options[option] = value


def test_apply_fingerprint_strips_padding_extension_from_tls_extension_order(
    monkeypatch,
):
    curl = FakeCurl()
    fingerprint = Fingerprint(tls_extension_order="0-21-11")
    toggle_extensions_by_ids = Mock()
    monkeypatch.setattr(
        "curl_cffi.requests.utils.toggle_extensions_by_ids",
        toggle_extensions_by_ids,
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    toggle_extensions_by_ids.assert_called_once_with(curl, {0, 11})
    assert curl.options[CurlOpt.TLS_EXTENSION_ORDER] == "0-11"


def test_apply_fingerprint_skips_extension_order_when_permuting(monkeypatch):
    curl = FakeCurl()
    fingerprint = Fingerprint(
        tls_extension_order="0-23-65281-11",
        tls_permute_extensions=True,
    )
    toggle_extensions_by_ids = Mock()
    monkeypatch.setattr(
        "curl_cffi.requests.utils.toggle_extensions_by_ids",
        toggle_extensions_by_ids,
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    toggle_extensions_by_ids.assert_called_once_with(curl, {0, 23, 65281, 11})
    assert CurlOpt.TLS_EXTENSION_ORDER not in curl.options
    assert curl.options[CurlOpt.SSL_PERMUTE_EXTENSIONS] == 1


def test_apply_fingerprint_rewrites_kyber_supported_group_alias():
    curl = FakeCurl()
    fingerprint = Fingerprint(tls_supported_groups=["X25519Kyber768", "P-256"])

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.SSL_EC_CURVES] == "X25519Kyber768Draft00:P-256"


def test_apply_fingerprint_with_tls_extension_order_respects_cert_compression():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        tls_extension_order="0-23-65281-10-11-16-5-13-18-51-45-43-27",
        tls_cert_compression=["zlib"],
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.SSL_CERT_COMPRESSION] == "zlib"


def test_apply_fingerprint_empty_host_uses_curl_generated_host():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        headers={
            "User-Agent": "test-agent",
            "Host": "",
            "Connection": "Keep-Alive",
        },
        header_order="User-Agent,Host,Connection",
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=True,
    )

    assert curl.options[CurlOpt.HTTPHEADER] == [
        b"User-Agent: test-agent",
        b"Connection: Keep-Alive",
    ]
    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "User-Agent,Host,Connection"


def test_apply_fingerprint_sets_http3_and_websocket_options():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        http3_headers={"User-Agent": "h3-agent", "Accept": "text/html"},
        http3_header_order="User-Agent,Accept",
        http3_tls_supported_groups=["X25519Kyber768", "P-256"],
        ws_headers={"User-Agent": "ws-agent", "Origin": "https://example.com"},
        ws_header_order="User-Agent,Origin",
        ws_disable_session_ticket=True,
        ws_tls_cert_compression=["zlib", "brotli"],
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=True,
    )

    assert curl.options[CurlOpt.HTTP3_HTTPHEADER] == [
        b"User-Agent: h3-agent",
        b"Accept: text/html",
    ]
    assert curl.options[CurlOpt.HTTP3_HTTPHEADER_ORDER] == "User-Agent,Accept"
    assert curl.options[CurlOpt.HTTP3_SSL_EC_CURVES] == "X25519Kyber768Draft00:P-256"
    assert curl.options[CurlOpt.WS_HTTPHEADER] == [
        b"User-Agent: ws-agent",
        b"Origin: https://example.com",
    ]
    assert curl.options[CurlOpt.WS_HTTPHEADER_ORDER] == "User-Agent,Origin"
    assert curl.options[CurlOpt.WS_SSL_DISABLE_TICKET] == 1
    assert curl.options[CurlOpt.WS_SSL_CERT_COMPRESSION] == "zlib,brotli"


def test_apply_fingerprint_can_disable_websocket_cert_compression():
    curl = FakeCurl()
    fingerprint = Fingerprint(ws_tls_cert_compression=[])

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.WS_SSL_CERT_COMPRESSION] == ""


def test_set_extra_fp_sets_header_order():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(header_order="User-Agent,Host,Connection")

    set_extra_fp(curl, extra_fp)

    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "User-Agent,Host,Connection"
