import contextlib
import os
import threading
import time
from typing import Any

import pytest
import uvicorn
from litestar import Litestar, get

ENVIRONMENT_VARIABLES = {
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSLKEYLOGFILE",
}


@pytest.fixture(scope="function", autouse=True)
def clean_environ():
    """Keeps os.environ clean for every test without having to mock os.environ"""
    original_environ = os.environ.copy()
    os.environ.clear()
    os.environ.update(
        {
            k: v
            for k, v in original_environ.items()
            if k not in ENVIRONMENT_VARIABLES and k.lower() not in ENVIRONMENT_VARIABLES
        }
    )
    yield
    os.environ.clear()
    os.environ.update(original_environ)


class Server(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True
            thread.join()

    @property
    def url(self):
        return f"http://{self.config.host}:{self.config.port}"


def _build_legacy_fingerprint_response() -> dict[str, Any]:
    profiles = []
    for i in range(10):
        fingerprint = {
            "client": "legacy",
            "client_version": str(100 + i),
            "os": "macos",
            "os_version": "14.0",
            "tls_version": "1.2",
            "tls_ciphers": [
                "TLS_AES_128_GCM_SHA256",
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256",
            ],
            "tls_supported_groups": ["X25519", "P-256", "P-384", "P-521"],
            "tls_signature_hashes": [
                "ecdsa_secp256r1_sha256",
                "rsa_pss_rsae_sha256",
                "rsa_pkcs1_sha256",
            ],
            "tls_alpn": True,
            "tls_alps": True,
            "tls_cert_compression": ["zlib"],
            "tls_session_ticket": True,
            "tls_extension_order": "65281-35-23-16-0-11-45-43-5-10",
            "tls_grease": True,
            "http2_settings": "1:65536;3:1000;4:6291456;6:262144",
            "http2_window_update": 15663105,
            "http2_pseudo_headers_order": "masp",
        }
        profiles.append(
            {
                "id": i,
                "name": f"legacy{100 + i}",
                "fingerprint": fingerprint,
                "min_supported_version": "0.14.0",
                "updated_at": "2025-08-30T00:00:00",
                "created_at": "2025-08-30T00:00:00",
            }
        )
    return _wrap_profiles(profiles)


def _build_v2_fingerprint_response() -> dict[str, Any]:
    profiles = []
    for i in range(10):
        fingerprint = {
            "client": "testing",
            "client_version": str(100 + i),
            "os": "macos",
            "os_version": "14.0",
            "http2": {
                "tls": {
                    "version": "1.2",
                    "ciphers": [
                        "TLS_AES_128_GCM_SHA256",
                        "TLS_AES_256_GCM_SHA384",
                        "TLS_CHACHA20_POLY1305_SHA256",
                    ],
                    "alpn": True,
                    "alps": True,
                    "cert_compression": ["brotli"],
                    "signature_hashes": [
                        "ecdsa_secp256r1_sha256",
                        "rsa_pss_rsae_sha256",
                        "rsa_pkcs1_sha256",
                    ],
                    "sig_hash_algs": (
                        "ecdsa_secp256r1_sha256,rsa_pss_rsae_sha256,rsa_pkcs1_sha256"
                    ),
                    "key_shares_limit": 2,
                    "supported_groups": ["X25519", "P-256", "P-384", "P-521"],
                    "session_ticket": True,
                    "extension_order": "65281-35-23-16-0-11-45-43-5-10",
                    "delegated_credentials": [],
                    "record_size_limit": None,
                    "grease": True,
                    "use_new_alps_codepoint": False,
                    "signed_cert_timestamps": True,
                    "ech": None,
                    "permute_extensions": False,
                },
                "settings": "1:65536;3:1000;4:6291456;6:262144",
                "pseudo_headers_order": "masp",
                "headers": [
                    {"name": "user-agent", "value": "testing-agent"},
                    {"name": "accept", "value": "text/html"},
                ],
                "header_lang": "en-US,en;q=0.9",
                "header_order": ["user-agent", "accept"],
                "window_update": 15663105,
                "stream_weight": None,
                "stream_exclusive": None,
                "no_priority": False,
                "priority_weight": 256,
                "priority_exclusive": 1,
                "split_cookies": True,
                "form_boundary": "webkit",
            },
            "http3": {
                "tls": {
                    "version": "1.2",
                    "ciphers": ["TLS_AES_128_GCM_SHA256"],
                    "alpn": True,
                    "alps": True,
                    "cert_compression": ["brotli"],
                    "signature_hashes": ["rsa_pss_rsae_sha256"],
                    "sig_hash_algs": "rsa_pss_rsae_sha256",
                    "key_shares_limit": 2,
                    "supported_groups": ["X25519", "P-256"],
                    "session_ticket": False,
                    "extension_order": "0-10-13-16-27-43-45-51",
                    "delegated_credentials": [],
                    "record_size_limit": None,
                    "grease": False,
                    "use_new_alps_codepoint": True,
                    "signed_cert_timestamps": False,
                    "ech": "true",
                    "permute_extensions": False,
                },
                "settings": "1:65536;6:262144;7:100",
                "pseudo_headers_order": "pmsa",
                "headers": [
                    {"name": "accept", "value": "text/html"},
                    {"name": "user-agent", "value": "testing-h3-agent"},
                ],
                "header_lang": "en-US,en;q=0.9",
                "header_order": ["accept", "user-agent"],
                "quic_transport_parameters": "17:1@1;32:65536",
            },
        }
        profiles.append(
            {
                "id": i,
                "name": f"testing{100 + i}",
                "client": "testing",
                "version": str(100 + i),
                "os": "macos",
                "os_version": "14.0",
                "min_supported_version": "0.15.1",
                "status": "pro",
                "http2_source_id": f"http2-source-{100 + i}",
                "http3_source_id": f"http3-source-{100 + i}",
                "created_at": "2026-05-25T00:00:00.000Z",
                "updated_at": "2026-05-25T00:00:00.000Z",
                "fingerprint": fingerprint,
            }
        )
    return _wrap_profiles(profiles)


def _wrap_profiles(profiles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pagination": {
            "skip": 0,
            "limit": 10,
            "total": len(profiles),
            "has_more": False,
            "next_skip": None,
        },
        "data": profiles,
    }


@get("/v1/fingerprints", sync_to_thread=False)
def get_legacy_fingerprints() -> dict[str, Any]:
    return _build_legacy_fingerprint_response()


@get("/v2/fingerprints", sync_to_thread=False)
def get_v2_fingerprints() -> dict[str, Any]:
    return _build_v2_fingerprint_response()


@get("/raw/{source_id:str}", sync_to_thread=False)
def get_raw_fingerprint(source_id: str) -> dict[str, Any]:
    return {
        "id": source_id,
        "fingerprint": {
            "tls": {
                "ja3": "771,4865-4866,10-23-35,29-23,0",
            },
            "http2": {
                "akamai_fingerprint_hash": source_id,
            },
        },
    }


app = Litestar(
    route_handlers=[
        get_legacy_fingerprints,
        get_v2_fingerprints,
        get_raw_fingerprint,
    ]
)


@pytest.fixture(scope="session")
def api_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=2952, log_level="info")
    server = Server(config=config)
    with server.run_in_thread():
        yield server
