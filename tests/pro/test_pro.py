import json
import os
from urllib.parse import parse_qs, urlparse

import pytest

from curl_cffi.curl import CurlError
from curl_cffi.fingerprints import FingerprintManager, FingerprintUpdateError


TESTING_API_KEY = "imp_alizee-lyonnet"


@pytest.fixture(scope="session", autouse=True)
def setup_pro(tmp_path_factory):
    os.environ["IMPERSONATE_CONFIG_DIR"] = str(
        tmp_path_factory.mktemp("impersonate-pro-tests")
    )
    # login before testing starts
    FingerprintManager.set_api_key(api_key=TESTING_API_KEY)
    yield


@pytest.fixture(autouse=True)
def clear_fingerprint_files():
    for path in (
        FingerprintManager.get_fingerprint_path(),
        FingerprintManager.get_fingerprint_v2_path(),
    ):
        if os.path.exists(path):
            os.unlink(path)
    FingerprintManager.load_fingerprints.cache_clear()
    yield
    FingerprintManager.load_fingerprints.cache_clear()


def test_update_fingerprints(api_server):
    updated = FingerprintManager.update_fingerprints(f"{api_server.url}/v2")
    fingerprints = FingerprintManager.load_fingerprints()
    assert updated == 10
    assert "testing100" in fingerprints
    assert "testing101" in fingerprints

    assert not os.path.exists(FingerprintManager.get_fingerprint_path())
    with open(FingerprintManager.get_fingerprint_v2_path()) as f:
        cache = json.load(f)
    assert cache["version"] == 2
    assert "testing100" in cache["data"]
    assert cache["data"]["testing100"]["http2"]["tls"]["version"] == "1.2"
    assert cache["data"]["testing100"]["http3"]["tls"]["extension_order"] == (
        "0-10-13-16-27-43-45-51"
    )


def test_update_fingerprints_reads_legacy_api(api_server):
    updated = FingerprintManager.update_fingerprints(f"{api_server.url}/v1")
    fingerprints = FingerprintManager.load_fingerprints()

    assert updated == 10
    assert os.path.exists(FingerprintManager.get_fingerprint_path())
    assert not os.path.exists(FingerprintManager.get_fingerprint_v2_path())
    assert "legacy100" in fingerprints
    assert "testing100" not in fingerprints


def test_update_fingerprints_reads_paginated_api(monkeypatch):
    urls = []

    def fetch_payload(url, headers):
        urls.append(url)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        skip = int(query["skip"][0])
        limit = int(query["limit"][0])
        assert limit == 100

        total = 102
        end = min(skip + limit, total)
        items = [
            {
                "name": f"testing{i}",
                "fingerprint": {
                    "client": "testing",
                    "client_version": str(i),
                },
            }
            for i in range(skip, end)
        ]
        return json.dumps(
            {
                "pagination": {
                    "skip": skip,
                    "limit": limit,
                    "total": total,
                    "has_more": end < total,
                    "next_skip": end if end < total else None,
                },
                "data": items,
            }
        ).encode()

    monkeypatch.setattr(
        FingerprintManager,
        "_fetch_fingerprint_payload",
        staticmethod(fetch_payload),
    )

    updated = FingerprintManager.update_fingerprints("https://api.test/v2")
    fingerprints = FingerprintManager.load_fingerprints()

    assert updated == 102
    assert urls == [
        "https://api.test/v2/fingerprints?skip=0&limit=100",
        "https://api.test/v2/fingerprints?skip=100&limit=100",
    ]
    assert "testing0" in fingerprints
    assert "testing101" in fingerprints


def test_single_fingerprint(api_server):
    FingerprintManager.update_fingerprints(f"{api_server.url}/v2")
    fingerprints = FingerprintManager.load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2.settings == "1:65536;3:1000;4:6291456;6:262144"
    assert testing100.http2.pseudo_headers_order == "masp"
    assert testing100.http2.tls.supported_groups == [
        "X25519",
        "P-256",
        "P-384",
        "P-521",
    ]
    assert testing100.http3.tls.extension_order == "0-10-13-16-27-43-45-51"


def test_fetch_fingerprint_payload_raises_access_error(monkeypatch):
    class DummyCurl:
        def setopt(self, option, value):
            pass

        def perform(self):
            raise CurlError(
                "Failed to perform, curl: (6) Could not resolve host: api.test. "
                "See https://curl.se/libcurl/c/libcurl-errors.html first for more "
                "details."
            )

        def close(self):
            pass

    monkeypatch.setattr("curl_cffi.fingerprints.Curl", DummyCurl)

    with pytest.raises(
        FingerprintUpdateError, match="Failed to access fingerprint endpoint"
    ) as exc_info:
        FingerprintManager._fetch_fingerprint_payload(
            "https://api.test/fingerprints", {}
        )

    assert str(exc_info.value).startswith(
        "Failed to access fingerprint endpoint at "
        "https://api.test/fingerprints: Failed to perform, curl: (6) "
    )
