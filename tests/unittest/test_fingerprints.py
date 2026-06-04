import json
import os

import pytest

import curl_cffi
from curl_cffi.fingerprints import FingerprintManager, _get_default_config_dir


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
                    "headers": {
                        "User-Agent": "fingerprint-ua",
                        "Accept": "text/html",
                    }
                }
            }
        )
    )

    fingerprint = curl_cffi.get_fingerprint("edge_146_macos_26")

    assert fingerprint.headers["User-Agent"] == "fingerprint-ua"
    fingerprint.headers["User-Agent"] = "custom-ua"
    assert fingerprint.headers["User-Agent"] == "custom-ua"
    assert FingerprintManager.get_fingerprint("edge_146_macos_26").headers[
        "User-Agent"
    ] == ("fingerprint-ua")


def test_get_fingerprint_parses_nested_protocol_fingerprints(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPERSONATE_CONFIG_DIR", str(tmp_path))
    fingerprint_path = tmp_path / "fingerprints.json"
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
                        "header_order": "user-agent,accept",
                        "headers": {
                            "accept": "*/*",
                            "user-agent": "test-agent",
                        },
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
                        "header_order": "user-agent,priority",
                        "headers": {
                            "priority": "u=1, i",
                            "user-agent": "test-agent",
                        },
                        "header_lang": "en-US,en;q=0.9",
                        "quic_transport_parameters": "3:4",
                    },
                    }
                }
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
    assert fingerprint.http2.header_order == "user-agent,accept"
    assert fingerprint.http2.headers == {
        "accept": "*/*",
        "user-agent": "test-agent",
    }
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
    assert fingerprint.http3.header_order == "user-agent,priority"
    assert fingerprint.http3.headers == {
        "priority": "u=1, i",
        "user-agent": "test-agent",
    }
    assert fingerprint.http3.header_lang == "en-US,en;q=0.9"
    assert fingerprint.http3.quic_transport_parameters == "3:4"

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
    assert fingerprint.headers == {}
