import contextlib
import json
import os
import threading
import time
from typing import Any

import pytest
import uvicorn
from litestar import Litestar, get
from curl_cffi.fingerprints import Fingerprint
import dataclasses

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


@get("/fingerprints", sync_to_thread=False)
def get_fingerprints() -> list[dict[str, Any]]:
    profiles = []
    for i in range(10):
        fingerprint = Fingerprint(
            client="testing",
            client_version=str(100 + i),
            os="macos",
            os_version="14.0",
            http_version="v2",
            tls_version="1.2",
            tls_ciphers=[
                "TLS_AES_128_GCM_SHA256",
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256",
                "TLS_ECDHE_ECDSA_WITH_AES_128_GCM_SHA256",
                "TLS_ECDHE_RSA_WITH_AES_128_GCM_SHA256",
                "TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384",
                "TLS_ECDHE_RSA_WITH_AES_256_GCM_SHA384",
            ],
            tls_supported_groups=["X25519", "P-256", "P-384", "P-521"],
            tls_signature_hashes=[
                "ecdsa_secp256r1_sha256",
                "ecdsa_secp384r1_sha384",
                "ecdsa_secp521r1_sha512",
                "rsa_pss_rsae_sha256",
                "rsa_pss_rsae_sha384",
                "rsa_pss_rsae_sha512",
                "rsa_pkcs1_sha256",
                "rsa_pkcs1_sha384",
                "rsa_pkcs1_sha512",
                "ecdsa_sha1",
                "rsa_pkcs1_sha1",
            ],
            tls_alpn=True,
            tls_alps=True,
            tls_cert_compression=["zlib"],
            tls_session_ticket=True,
            tls_extension_order="65281-35-23-16-0-11-45-43-5-10-27-18-51-13-17513-21",
            tls_grease=True,
            http2_settings="1:65536;3:1000;4:6291456;6:262144",
            http2_window_update=15663105,
            http2_pseudo_headers_order="masp",
        )
        profiles.append(
            {
                "id": i,
                "name": f"testing{100 + i}",
                "data": json.dumps(dataclasses.asdict(fingerprint)),
                "min_supported_version": "0.14.0",
                "updated_at": "2025-08-30T00:00:00",
                "created_at": "2025-08-30T00:00:00",
            }
        )
    return profiles


@get("/marketshare", sync_to_thread=False)
def get_market_share() -> None: ...


app = Litestar(route_handlers=[get_fingerprints, get_market_share])


@pytest.fixture(scope="session")
def api_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=2952, log_level="info")
    server = Server(config=config)
    with server.run_in_thread():
        yield server
