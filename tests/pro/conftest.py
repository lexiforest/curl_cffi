import contextlib
import os
import threading
import time
import typing

import pytest
import uvicorn
from fastapi import FastAPI
from uvicorn.config import Config
from uvicorn.main import Server
from curl_cffi.pro import Profile
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


class FileServer(uvicorn.Server):
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


app = FastAPI()


@app.get("/profiles")
def get_profiles():
    profiles = []
    for i in range(10):
        profile = Profile(
            http_version="v2",
            ssl_version="tlsv1_2",
            ciphers=[
                "TLS_AES_128_GCM_SHA256",
                "TLS_AES_256_GCM_SHA384",
                "TLS_CHACHA20_POLY1305_SHA256",
                "ECDHE-ECDSA-AES128-GCM-SHA256",
                "ECDHE-RSA-AES128-GCM-SHA256",
                "ECDHE-ECDSA-AES256-GCM-SHA384",
                "ECDHE-RSA-AES256-GCM-SHA384",
                "ECDHE-ECDSA-CHACHA20-POLY1305",
                "ECDHE-RSA-CHACHA20-POLY1305",
                "ECDHE-RSA-AES128-SHA",
                "ECDHE-RSA-AES256-SHA",
                "AES128-GCM-SHA256",
                "AES256-GCM-SHA384",
                "AES128-SHA",
                "AES256-SHA",
            ],
            curves=["X25519", "P-256", "P-384", "P-521"],
            signature_hashes=[
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
            npn=True,
            alpn=True,
            alps=True,
            cert_compression=["zlib"],
            tls_session_ticket=True,
            tls_extension_order="xxxxx",
            tls_grease=True,
        )
        profiles.append({
            "id": i,
            "target":f"testing{100 + i}",
            "client": "testing",
            "version": str(100 + i),
            "platform": "macos",
            "profile": dataclasses.asdict(profile),
            "min_supported_version": "0.14.0",
            "updated_at": "2025-08-30T00:00:00",
            "created_at": "2025-08-30T00:00:00",
        })
    return {
        "items": profiles,
    }


@app.get("/marketshare")
def get_market_share():
    ...


@pytest.fixture(scope="session")
def api_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=2952, log_level="info")
    server = FileServer(config=config)
    with server.run_in_thread():
        yield server
