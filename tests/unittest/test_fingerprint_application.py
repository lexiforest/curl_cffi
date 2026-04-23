from curl_cffi.const import CurlOpt
from curl_cffi.fingerprints import Fingerprint
from curl_cffi.requests.utils import _apply_fingerprint


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
    seen_extension_ids = None

    def fake_toggle_extensions_by_ids(_curl, extension_ids):
        nonlocal seen_extension_ids
        seen_extension_ids = extension_ids

    monkeypatch.setattr(
        "curl_cffi.requests.utils.toggle_extensions_by_ids",
        fake_toggle_extensions_by_ids,
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert seen_extension_ids == {0, 11}
    assert curl.options[CurlOpt.TLS_EXTENSION_ORDER] == "0-11"


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
