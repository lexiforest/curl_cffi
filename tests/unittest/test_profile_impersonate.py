from curl_cffi import CurlOpt, CurlSslVersion
from curl_cffi.pro import Profile
from curl_cffi.requests import utils


def test_set_impersonate_target_uses_profile(monkeypatch):
    seen = {}

    class DummyCurl:
        def impersonate(self, target, default_headers=True):
            return 1

        def setopt(self, option, value):
            seen[option] = value

    profile = Profile(
        tls_version="1.2",
        tls_ciphers=[
            "TLS_AES_128_GCM_SHA256",
            "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
        ],
        tls_alpn=True,
        tls_alps=False,
        tls_cert_compression=["brotli"],
        tls_signature_hashes=["rsa_pkcs1_sha256"],
        tls_key_shares_limit=1,
        tls_supported_groups=["X25519"],
        tls_session_ticket=True,
        tls_grease=True,
        http2_settings="1:65536",
        http2_window_update=15663105,
        http2_pseudo_headers_order="masp",
        headers={"accept": "text/html"},
    )

    monkeypatch.setattr(utils, "load_profiles", lambda: {"testing100": profile})

    header_lines = ["User-Agent: test"]
    utils.set_impersonate_target(
        DummyCurl(),
        target="testing100",
        default_headers=True,
        header_lines=header_lines,
    )

    assert (
        seen[CurlOpt.SSLVERSION]
        == CurlSslVersion.TLSv1_2 | CurlSslVersion.MAX_DEFAULT
    )
    assert seen[CurlOpt.SSL_CIPHER_LIST] == "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256"
    assert seen[CurlOpt.TLS13_CIPHERS] == "TLS_AES_128_GCM_SHA256"
    assert seen[CurlOpt.HTTP2_SETTINGS] == "1:65536"
    assert any(line.lower().startswith("accept:") for line in header_lines)
