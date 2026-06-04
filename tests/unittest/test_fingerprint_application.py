from curl_cffi.const import CurlHttpVersion, CurlOpt
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


def test_apply_fingerprint_sets_http3_sig_hash_algs():
    curl = FakeCurl()
    fingerprint = Fingerprint(http3_sig_hash_algs="rsa_pss_rsae_sha256")

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.HTTP3_SIG_HASH_ALGS] == "rsa_pss_rsae_sha256"


def test_apply_fingerprint_sets_nested_http3_options():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        http3={
            "tls": {
                "version": "1.3",
                "ciphers": ["TLS_AES_256_GCM_SHA384"],
                "alpn": True,
                "alps": True,
                "cert_compression": ["brotli"],
                "session_ticket": True,
                "extension_order": "0-10-13",
                "delegated_credentials": ["ecdsa_secp256r1_sha256"],
                "record_size_limit": 4001,
                "grease": True,
                "use_new_alps_codepoint": True,
                "signed_cert_timestamps": True,
                "ech": "true",
                "permute_extensions": True,
                "signature_hashes": ["rsa_pss_rsae_sha256"],
                "supported_groups": ["X25519MLKEM768", "X25519"],
                "key_shares_limit": 2,
            },
            "settings": "1:2",
            "pseudo_headers_order": "m,a,s,p",
            "header_order": "user-agent,accept",
            "headers": {
                "user-agent": "test-agent",
                "accept": "*/*",
            },
            "quic_transport_parameters": "3:4",
        },
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=True,
    )

    assert curl.options[CurlOpt.HTTP_VERSION] == CurlHttpVersion.V3
    assert curl.options[CurlOpt.SSL_CIPHER_LIST] == "TLS_AES_256_GCM_SHA384"
    assert curl.options[CurlOpt.SSL_ENABLE_ALPN] == 1
    assert curl.options[CurlOpt.SSL_ENABLE_ALPS] == 1
    assert curl.options[CurlOpt.SSL_ENABLE_TICKET] == 1
    assert curl.options[CurlOpt.TLS_GREASE] == 1
    assert curl.options[CurlOpt.TLS_USE_NEW_ALPS_CODEPOINT] == 1
    assert curl.options[CurlOpt.TLS_SIGNED_CERT_TIMESTAMPS] == 1
    assert curl.options[CurlOpt.SSL_CERT_COMPRESSION] == "brotli"
    assert curl.options[CurlOpt.TLS_DELEGATED_CREDENTIALS] == (
        "ecdsa_secp256r1_sha256"
    )
    assert curl.options[CurlOpt.SSL_PERMUTE_EXTENSIONS] == 1
    assert curl.options[CurlOpt.TLS_RECORD_SIZE_LIMIT] == 4001
    assert curl.options[CurlOpt.ECH] == "true"
    assert curl.options[CurlOpt.SSL_EC_CURVES] == "X25519MLKEM768:X25519"
    assert curl.options[CurlOpt.TLS_KEY_SHARES_LIMIT] == 2
    assert CurlOpt.TLS_EXTENSION_ORDER not in curl.options
    assert curl.options[CurlOpt.HTTP3_SETTINGS] == "1:2"
    assert curl.options[CurlOpt.HTTP3_PSEUDO_HEADERS_ORDER] == "masp"
    assert curl.options[CurlOpt.HTTP3_SIG_HASH_ALGS] == "rsa_pss_rsae_sha256"
    assert curl.options[CurlOpt.HTTP3_TLS_EXTENSION_ORDER] == "0-10-13"
    assert curl.options[CurlOpt.QUIC_TRANSPORT_PARAMETERS] == "3:4"
    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "user-agent,accept"
    assert curl.options[CurlOpt.HTTPHEADER] == [
        b"user-agent: test-agent",
        b"accept: */*",
    ]


def test_set_extra_fp_sets_header_order():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(header_order="User-Agent,Host,Connection")

    set_extra_fp(curl, extra_fp)

    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "User-Agent,Host,Connection"
