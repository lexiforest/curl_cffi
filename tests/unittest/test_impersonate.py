import pytest

from curl_cffi import requests
from curl_cffi.const import CurlHttpVersion, CurlSslVersion


def test_impersonate_with_version(server):
    # the test server does not understand http/2
    r = requests.get(str(server.url), impersonate="chrome120", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200
    r = requests.get(str(server.url), impersonate="safari17_0", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200


def test_impersonate_without_version(server):
    r = requests.get(str(server.url), impersonate="chrome", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200
    r = requests.get(str(server.url), impersonate="safari_ios", http_version=CurlHttpVersion.V1_1)
    assert r.status_code == 200


def test_impersonate_non_exist(server):
    with pytest.raises(requests.RequestsError, match="Impersonating"):
        requests.get(str(server.url), impersonate="edge2131")
    with pytest.raises(requests.RequestsError, match="Impersonating"):
        requests.get(str(server.url), impersonate="chrome2952")


# TODO implement local ja3/akamai verification server with th1.


@pytest.mark.skip(reason="warning is used")
def test_costomized_no_impersonate_coexist(server):
    with pytest.raises(requests.RequestsError):
        requests.get(str(server.url), impersonate="chrome", ja3=",,,,")
    with pytest.raises(requests.RequestsError):
        requests.get(str(server.url), impersonate="chrome", akamai="|||")


def test_customized_ja3_chrome126():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "0-65037-27-51-13-43-5-18-17513-65281-23-10-45-35-11-16,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    assert r["ja3_text"] == ja3


@pytest.mark.skip(reason="not working")
def test_customized_ja3_tls_version():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "770,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "0-65037-27-51-13-43-5-18-17513-65281-23-10-45-35-11-16,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    tls_version, _, _, _, _ = r["ja3_text"].split(",")
    assert tls_version == "770"


def test_customized_ja3_ciphers():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171,"
        "0-65037-27-51-13-43-5-18-17513-65281-23-10-45-35-11-16,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, ciphers, _, _, _ = r["ja3_text"].split(",")
    assert ciphers == "4865-4866-4867-49195-49199-49196-49200-52393-52392-49171"


# TODO change to parameterized test
def test_customized_ja3_extensions():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "65037-65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions == "65037-65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51"

    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions == "65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51"

    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "65281-0-11-23-27-16-17513-10-35-43-45-13-51,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions == "65281-0-11-23-27-16-17513-10-35-43-45-13-51"

    # removed enable session_ticket()
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "65281-0-11-23-5-18-27-16-17513-10-43-45-13-51,25497-29-23-24,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions == "65281-0-11-23-5-18-27-16-17513-10-43-45-13-51"


def test_customized_ja3_curves():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "0-65037-27-51-13-43-5-18-17513-65281-23-10-45-35-11-16,25497-24-23-29,0"
    )
    r = requests.get(url, ja3=ja3).json()
    _, _, _, curves, _ = r["ja3_text"].split(",")
    assert curves == "25497-24-23-29"


def test_customized_akamai_chrome126():
    url = "https://tls.browserleaks.com/json"
    akamai = "1:65536;2:0;4:6291456;6:262144|15663105|0|m,a,s,p"
    r = requests.get(url, akamai=akamai).json()
    assert r["akamai_text"] == akamai


def test_customized_akamai_safari():
    url = "https://tls.browserleaks.com/json"
    akamai = "2:0;4:4194304;3:100|10485760|0|m,s,p,a"
    r = requests.get(url, akamai=akamai).json()
    assert r["akamai_text"] == akamai

    # test_tls_peet_ws_settings
    r = requests.get(url, akamai=akamai.replace(";", ",")).json()
    assert r["akamai_text"] == akamai


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_sig_hash_algs():
    url = "https://tls.peet.ws/api/all"
    safari_algs = [
        "ecdsa_secp256r1_sha256",
        "rsa_pss_rsae_sha256",
        "rsa_pkcs1_sha256",
        "ecdsa_secp384r1_sha384",
        "ecdsa_sha1",
        "rsa_pss_rsae_sha384",
        "rsa_pss_rsae_sha384",
        "rsa_pkcs1_sha384",
        "rsa_pss_rsae_sha512",
        "rsa_pkcs1_sha512",
        "rsa_pkcs1_sha1",
    ]
    fp = requests.ExtraFingerprints(tls_signature_algorithms=safari_algs)
    r = requests.get(url, extra_fp=fp).json()
    result_algs = []
    for ex in r["tls"]["extensions"]:
        if ex["name"] == "signature_algorithms (13)":
            result_algs = ex["signature_algorithms"]
    assert safari_algs == result_algs


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_tls_min_version():
    url = "https://tls.peet.ws/api/all"
    safari_min_version = CurlSslVersion.TLSv1_0
    fp = requests.ExtraFingerprints(tls_min_version=safari_min_version)
    r = requests.get(url, extra_fp=fp).json()
    for ex in r["tls"]["extensions"]:
        if ex["name"] == "supported_versions (43)":
            # TLS 1.0 1.1, 1.2, 1.3
            assert len(ex["versions"]) >= 4


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_grease():
    url = "https://tls.peet.ws/api/all"
    fp = requests.ExtraFingerprints(tls_grease=True)
    r = requests.get(url, extra_fp=fp).json()
    assert "TLS_GREASE" in r["tls"]["ciphers"][0]


def test_customized_extra_fp_permute():
    url = "https://tls.browserleaks.com/json"
    ja3 = (
        "771,4865-4866-4867-49195-49199-49196-49200-52393-52392-49171-49172-156-157-47-53,"
        "65037-65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51,25497-29-23-24,0"
    )

    r = requests.get(url, ja3=ja3).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions == "65037-65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51"

    r = requests.get(
        url, ja3=ja3, extra_fp=requests.ExtraFingerprints(tls_permute_extensions=True)
    ).json()
    _, _, extensions, _, _ = r["ja3_text"].split(",")
    assert extensions != "65037-65281-0-11-23-5-18-27-16-17513-10-35-43-45-13-51"


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_cert_compression():
    url = "https://tls.peet.ws/api/all"
    fp = requests.ExtraFingerprints(tls_cert_compression="zlib")
    r = requests.get(url, extra_fp=fp).json()
    result_algs = []
    for ex in r["tls"]["extensions"]:
        if ex["name"] == "compress_certificate (27)":
            result_algs = ex["algorithms"]
    assert result_algs[0] == "zlib (1)"


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_stream_weight():
    url = "https://tls.peet.ws/api/all"
    fp = requests.ExtraFingerprints(http2_stream_weight=64)
    r = requests.get(url, extra_fp=fp).json()
    assert r["http2"]["sent_frames"][2]["priority"]["weight"] == 64


@pytest.mark.skip(reason="Unstable API")
def test_customized_extra_fp_stream_exclusive():
    url = "https://tls.peet.ws/api/all"
    fp = requests.ExtraFingerprints(http2_stream_exclusive=0)
    r = requests.get(url, extra_fp=fp).json()
    assert r["http2"]["sent_frames"][2]["priority"]["exclusive"] == 0
