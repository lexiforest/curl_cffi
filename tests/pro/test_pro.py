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


def test_update_fingerprints(api_server):
    updated = FingerprintManager.update_fingerprints(api_server.url)
    fingerprints = FingerprintManager.load_fingerprints()
    assert updated == 10
    assert "testing100" in fingerprints
    assert "testing101" in fingerprints


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

    updated = FingerprintManager.update_fingerprints("https://api.test")
    fingerprints = FingerprintManager.load_fingerprints()

    assert updated == 102
    assert urls == [
        "https://api.test/fingerprints?skip=0&limit=100",
        "https://api.test/fingerprints?skip=100&limit=100",
    ]
    assert "testing0" in fingerprints
    assert "testing101" in fingerprints


def test_single_fingerprint(api_server):
    FingerprintManager.update_fingerprints(api_server.url)
    fingerprints = FingerprintManager.load_fingerprints()
    testing100 = fingerprints["testing100"]
    assert testing100.http2_settings == "1:65536;3:1000;4:6291456;6:262144"
    assert testing100.http2_pseudo_headers_order == "masp"
    assert testing100.tls_supported_groups == ["X25519", "P-256", "P-384", "P-521"]


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
