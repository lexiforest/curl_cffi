import json
import os

import pytest

import curl_cffi
from curl_cffi.fingerprints import (
    API_ROOT_V1,
    API_ROOT_V2,
    Fingerprint,
    FingerprintManager,
    _get_default_config_dir,
)


@pytest.fixture(autouse=True)
def clear_fingerprint_cache():
    FingerprintManager.load_fingerprints.cache_clear()
    yield
    FingerprintManager.load_fingerprints.cache_clear()


def test_get_default_config_dir_linux_xdg(monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX default config path test")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg-config")

    assert _get_default_config_dir() == "/tmp/xdg-config/impersonate"


def test_get_default_config_dir_linux_fallback(monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX default config path test")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", "/home/tester")

    assert _get_default_config_dir() == "/home/tester/.config/impersonate"


def test_get_default_config_dir_macos(monkeypatch):
    if os.name != "posix":
        pytest.skip("POSIX default config path test")
    monkeypatch.setenv("HOME", "/Users/tester")

    assert _get_default_config_dir() == "/Users/tester/.config/impersonate"


def test_get_default_config_dir_windows(monkeypatch):
    if os.name != "nt":
        pytest.skip("Windows default config path test")
    monkeypatch.setenv("APPDATA", r"C:\Users\tester\AppData\Roaming")

    assert _get_default_config_dir() == r"C:\Users\tester\AppData\Roaming\impersonate"


def test_get_config_dir_prefers_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    assert FingerprintManager.get_config_dir() == str(tmp_path)


def test_get_fingerprint_v2_path(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    assert FingerprintManager.get_fingerprint_v2_path() == str(
        tmp_path / "fingerprints_v2.json"
    )


def test_get_api_root_defaults_to_v2(monkeypatch):
    monkeypatch.delenv("IMPERSONATE_API_ROOT", raising=False)
    monkeypatch.delenv("IMPERSONATE_API_VERSION", raising=False)

    assert FingerprintManager.get_api_root() == API_ROOT_V2


@pytest.mark.parametrize("api_version", ["1", "v1", "V1"])
def test_get_api_root_uses_v1_version_override(monkeypatch, api_version):
    monkeypatch.delenv("IMPERSONATE_API_ROOT", raising=False)
    monkeypatch.setenv("IMPERSONATE_API_VERSION", api_version)

    assert FingerprintManager.get_api_root() == API_ROOT_V1


@pytest.mark.parametrize("api_version", ["2", "v2", "V2"])
def test_get_api_root_uses_v2_version_override(monkeypatch, api_version):
    monkeypatch.delenv("IMPERSONATE_API_ROOT", raising=False)
    monkeypatch.setenv("IMPERSONATE_API_VERSION", api_version)

    assert FingerprintManager.get_api_root() == API_ROOT_V2


def test_get_api_root_prefers_explicit_root_over_version(monkeypatch):
    monkeypatch.setenv("IMPERSONATE_API_ROOT", "https://api.test/custom")
    monkeypatch.setenv("IMPERSONATE_API_VERSION", "1")

    assert FingerprintManager.get_api_root() == "https://api.test/custom"


def test_get_api_root_rejects_invalid_version(monkeypatch):
    monkeypatch.delenv("IMPERSONATE_API_ROOT", raising=False)
    monkeypatch.setenv("IMPERSONATE_API_VERSION", "3")

    with pytest.raises(ValueError, match="IMPERSONATE_API_VERSION"):
        FingerprintManager.get_api_root()


def test_get_api_key_prefers_environment_override(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api_key": "imp_config"}))
    monkeypatch.setenv("IMPERSONATE_API_KEY", "imp_env")

    assert FingerprintManager.get_api_key() == "imp_env"


def test_get_api_key_falls_back_to_config_file(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"api_key": "imp_config"}))
    monkeypatch.delenv("IMPERSONATE_API_KEY", raising=False)

    assert FingerprintManager.get_api_key() == "imp_config"


def test_get_fingerprint_returns_editable_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    fingerprint_path = tmp_path / "fingerprints.json"
    fingerprint_path.write_text(
        json.dumps(
            {
                "edge_146_macos_26": {
                    "headers": [
                        {"name": "User-Agent", "value": "fingerprint-ua"},
                        {"name": "Accept", "value": "text/html"},
                    ]
                }
            }
        )
    )

    fingerprint = curl_cffi.get_fingerprint("edge_146_macos_26")

    assert fingerprint.headers[0]["value"] == "fingerprint-ua"
    fingerprint.headers[0]["value"] = "custom-ua"
    assert fingerprint.headers[0]["value"] == "custom-ua"
    assert FingerprintManager.get_fingerprint("edge_146_macos_26").headers[0][
        "value"
    ] == ("fingerprint-ua")


def test_legacy_fingerprint_fields_are_nested_aliases():
    fingerprint = Fingerprint(
        tls_version="1.3",
        tls_ciphers=["TLS_AES_128_GCM_SHA256"],
        headers=[{"name": "User-Agent", "value": "test-agent"}],
        http2_settings="1:65536",
        http3_settings="1:2",
    )

    assert fingerprint.http2.tls.version == "1.3"
    assert fingerprint.http3.tls.version == "1.3"
    assert fingerprint.tls_version == "1.3"
    assert fingerprint.http2.headers == [{"name": "User-Agent", "value": "test-agent"}]
    assert fingerprint.http3.headers == [{"name": "User-Agent", "value": "test-agent"}]
    assert fingerprint.http2.settings == "1:65536"
    assert fingerprint.http3.settings == "1:2"

    fingerprint.tls_version = "1.2"
    fingerprint.http2_settings = "1:1"

    assert fingerprint.http2.tls.version == "1.2"
    assert fingerprint.http3.tls.version == "1.3"
    assert fingerprint.http2.settings == "1:1"


def test_get_fingerprint_parses_nested_protocol_fingerprints(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    fingerprint_path = tmp_path / "fingerprints_v2.json"
    fingerprint_path.write_text(
        json.dumps(
            {
                "version": 2,
                "data": {
                    "chrome_147": {
                        "http2": {
                            "tls": {
                                "version": "1.3",
                                "ciphers": ["TLS_AES_128_GCM_SHA256"],
                                "alpn": True,
                                "alps": True,
                                "cert_compression": ["brotli"],
                                "session_ticket": True,
                                "extension_order": "0-11-10",
                                "delegated_credentials": ["ecdsa_secp256r1_sha256"],
                                "record_size_limit": 4001,
                                "grease": True,
                                "use_new_alps_codepoint": True,
                                "signed_cert_timestamps": True,
                                "ech": "true",
                                "permute_extensions": True,
                                "signature_hashes": ["ecdsa_secp256r1_sha256"],
                                "sig_hash_algs": "ecdsa_secp256r1_sha256",
                                "supported_groups": ["X25519", "P-256"],
                                "key_shares_limit": 1,
                            },
                            "settings": "1:65536",
                            "pseudo_headers_order": "masp",
                            "header_order": ["user-agent", "accept"],
                            "headers": [
                                {"name": "accept", "value": "*/*"},
                                {"name": "user-agent", "value": "test-agent"},
                            ],
                            "header_lang": "en-US,en;q=0.9",
                            "window_update": 15663105,
                            "stream_weight": 220,
                            "stream_exclusive": 1,
                            "no_priority": False,
                            "priority_weight": 256,
                            "priority_exclusive": 1,
                            "split_cookies": True,
                            "form_boundary": "webkit",
                        },
                        "http3": {
                            "tls": {
                                "version": "1.3",
                                "ciphers": ["TLS_AES_256_GCM_SHA384"],
                                "extension_order": "0-10-13",
                                "signature_hashes": ["rsa_pss_rsae_sha256"],
                                "sig_hash_algs": "rsa_pss_rsae_sha256",
                                "supported_groups": ["X25519MLKEM768", "X25519"],
                                "key_shares_limit": 2,
                            },
                            "settings": "1:2",
                            "pseudo_headers_order": "m,a,s,p",
                            "header_order": ["user-agent", "priority"],
                            "headers": [
                                {"name": "priority", "value": "u=1, i"},
                                {"name": "user-agent", "value": "test-agent"},
                            ],
                            "header_lang": "en-US,en;q=0.9",
                            "quic_transport_parameters": "3:4",
                            "split_cookies": True,
                            "form_boundary": "webkit-h3",
                        },
                    }
                },
            }
        )
    )

    fingerprint = curl_cffi.get_fingerprint("chrome_147")

    assert fingerprint.http2.tls.version == "1.3"
    assert fingerprint.http2.tls.ciphers == ["TLS_AES_128_GCM_SHA256"]
    assert fingerprint.http2.tls.alpn is True
    assert fingerprint.http2.tls.alps is True
    assert fingerprint.http2.tls.cert_compression == ["brotli"]
    assert fingerprint.http2.tls.session_ticket is True
    assert fingerprint.http2.tls.extension_order == "0-11-10"
    assert fingerprint.http2.tls.delegated_credentials == ["ecdsa_secp256r1_sha256"]
    assert fingerprint.http2.tls.record_size_limit == 4001
    assert fingerprint.http2.tls.grease is True
    assert fingerprint.http2.tls.use_new_alps_codepoint is True
    assert fingerprint.http2.tls.signed_cert_timestamps is True
    assert fingerprint.http2.tls.ech == "true"
    assert fingerprint.http2.tls.permute_extensions is True
    assert fingerprint.http2.tls.signature_hashes == ["ecdsa_secp256r1_sha256"]
    assert fingerprint.http2.tls.sig_hash_algs == "ecdsa_secp256r1_sha256"
    assert fingerprint.http2.tls.supported_groups == ["X25519", "P-256"]
    assert fingerprint.http2.tls.key_shares_limit == 1
    assert fingerprint.http2.settings == "1:65536"
    assert fingerprint.http2.pseudo_headers_order == "masp"
    assert fingerprint.http2.header_order == ["user-agent", "accept"]
    assert fingerprint.http2.headers == [
        {"name": "accept", "value": "*/*"},
        {"name": "user-agent", "value": "test-agent"},
    ]
    assert fingerprint.http2.header_lang == "en-US,en;q=0.9"
    assert fingerprint.http2.window_update == 15663105
    assert fingerprint.http2.stream_weight == 220
    assert fingerprint.http2.stream_exclusive == 1
    assert fingerprint.http2.no_priority is False
    assert fingerprint.http2.priority_weight == 256
    assert fingerprint.http2.priority_exclusive == 1
    assert fingerprint.http2.split_cookies is True
    assert fingerprint.http2.form_boundary == "webkit"

    assert fingerprint.http3.tls.version == "1.3"
    assert fingerprint.http3.tls.ciphers == ["TLS_AES_256_GCM_SHA384"]
    assert fingerprint.http3.tls.extension_order == "0-10-13"
    assert fingerprint.http3.tls.signature_hashes == ["rsa_pss_rsae_sha256"]
    assert fingerprint.http3.tls.sig_hash_algs == "rsa_pss_rsae_sha256"
    assert fingerprint.http3.tls.supported_groups == ["X25519MLKEM768", "X25519"]
    assert fingerprint.http3.tls.key_shares_limit == 2
    assert fingerprint.http3.settings == "1:2"
    assert fingerprint.http3.pseudo_headers_order == "m,a,s,p"
    assert fingerprint.http3.header_order == ["user-agent", "priority"]
    assert fingerprint.http3.headers == [
        {"name": "priority", "value": "u=1, i"},
        {"name": "user-agent", "value": "test-agent"},
    ]
    assert fingerprint.http3.header_lang == "en-US,en;q=0.9"
    assert fingerprint.http3.quic_transport_parameters == "3:4"
    assert fingerprint.http3.split_cookies is True
    assert fingerprint.http3.form_boundary == "webkit-h3"

    assert fingerprint.tls_version == "1.3"
    assert fingerprint.tls_ciphers == ["TLS_AES_128_GCM_SHA256"]
    assert fingerprint.tls_alpn is True
    assert fingerprint.tls_alps is True
    assert fingerprint.tls_cert_compression == ["brotli"]
    assert fingerprint.tls_session_ticket is True
    assert fingerprint.tls_extension_order == "0-11-10"
    assert fingerprint.tls_delegated_credentials == ["ecdsa_secp256r1_sha256"]
    assert fingerprint.tls_record_size_limit == 4001
    assert fingerprint.tls_grease is True
    assert fingerprint.tls_use_new_alps_codepoint is True
    assert fingerprint.tls_signed_cert_timestamps is True
    assert fingerprint.tls_ech == "true"
    assert fingerprint.tls_permute_extensions is True
    assert fingerprint.tls_signature_hashes == ["ecdsa_secp256r1_sha256"]
    assert fingerprint.tls_supported_groups == ["X25519", "P-256"]
    assert fingerprint.http2_settings == "1:65536"
    assert fingerprint.http2_pseudo_headers_order == "masp"
    assert fingerprint.header_lang == "en-US,en;q=0.9"
    assert fingerprint.split_cookies is True
    assert fingerprint.form_boundary == "webkit"
    assert fingerprint.http2_window_update == 15663105
    assert fingerprint.http2_stream_weight == 220
    assert fingerprint.http2_stream_exclusive == 1
    assert fingerprint.http3_settings == "1:2"
    assert fingerprint.http3_pseudo_headers_order == "m,a,s,p"
    assert fingerprint.http3_sig_hash_algs == "rsa_pss_rsae_sha256"
    assert fingerprint.http3_tls_extension_order == "0-10-13"


def test_load_fingerprints_prefers_v2_cache_when_present(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    legacy_path = tmp_path / "fingerprints.json"
    v2_path = tmp_path / "fingerprints_v2.json"
    legacy_path.write_text(
        json.dumps(
            {
                "legacy_only": {
                    "client": "legacy",
                    "headers": [{"name": "User-Agent", "value": "legacy-agent"}],
                }
            }
        )
    )
    v2_path.write_text(
        json.dumps(
            {
                "version": 2,
                "data": {
                    "v2_only": {
                        "client": "v2",
                        "http2": {
                            "headers": [
                                {"name": "User-Agent", "value": "v2-agent"}
                            ],
                        },
                    }
                },
            }
        )
    )

    fingerprints = FingerprintManager.load_fingerprints()

    assert "v2_only" in fingerprints
    assert "legacy_only" not in fingerprints


def test_get_fingerprint_maps_legacy_http3_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    fingerprint_path = tmp_path / "fingerprints.json"
    fingerprint_path.write_text(
        json.dumps(
            {
                "chrome_legacy_h3": {
                    "http3_settings": "1:2",
                    "http3_pseudo_headers_order": "m,a,s,p",
                    "http3_sig_hash_algs": "rsa_pss_rsae_sha256",
                    "http3_tls_extension_order": "0-10-13",
                    "quic_transport_parameters": "3:4",
                }
            }
        )
    )

    fingerprint = curl_cffi.get_fingerprint("chrome_legacy_h3")

    assert fingerprint.http3.tls.version == ""
    assert fingerprint.http3.settings == "1:2"
    assert fingerprint.http3.pseudo_headers_order == "m,a,s,p"
    assert fingerprint.http3.tls.sig_hash_algs == "rsa_pss_rsae_sha256"
    assert fingerprint.http3.tls.extension_order == "0-10-13"
    assert fingerprint.http3.quic_transport_parameters == "3:4"


def test_get_fingerprint_unknown_target_raises_key_error(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    with pytest.raises(KeyError, match="Fingerprint target not found"):
        curl_cffi.get_fingerprint("missing-target")


def test_get_fingerprint_returns_native_target_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))

    fingerprint = curl_cffi.get_fingerprint("chrome120")

    assert fingerprint.client == "chrome"
    assert fingerprint.headers == []
