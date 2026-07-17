import asyncio
import queue
import threading
from unittest.mock import Mock

import pytest

from curl_cffi.const import CurlHttpVersion, CurlOpt, CurlSslVersion
from curl_cffi.curl import CURL_WRITEFUNC_ERROR, CURL_WRITEFUNC_PAUSE, CURLPAUSE_CONT
from curl_cffi.requests.impersonate import ExtraFingerprints
from curl_cffi.requests import utils


class FakeCurl:
    def __init__(self):
        self.options = {}
        self.pause_calls = []

    def setopt(self, option, value):
        self.options[option] = value

    def pause(self, action):
        self.pause_calls.append(action)
        return 0


def _set_stream_options(curl, queue_class, event_class):
    return utils.set_curl_options(
        curl,
        "GET",
        "https://example.com/",
        params_list=[None, None],
        headers_list=[None, None],
        cookies_list=[None, None],
        proxies_list=[None, None],
        verify_list=[True, None],
        stream=True,
        stream_queue_size=1,
        queue_class=queue_class,
        event_class=event_class,
    )


def test_sync_stream_queue_applies_interruptible_backpressure():
    curl = FakeCurl()
    _, _, _, q, _, _, control = _set_stream_options(curl, queue.Queue, threading.Event)
    write = curl.options[CurlOpt.WRITEFUNCTION]

    assert q.maxsize == 1
    assert write(b"first") == len(b"first")

    result = []
    started = threading.Event()

    def write_second_chunk():
        started.set()
        result.append(write(b"second"))

    writer = threading.Thread(target=write_second_chunk)
    writer.start()
    assert started.wait(timeout=1)
    writer.join(timeout=0.05)
    assert writer.is_alive()

    control.abort()
    writer.join(timeout=1)
    assert result == [CURL_WRITEFUNC_ERROR]


def test_async_stream_queue_pauses_and_resumes_curl():
    curl = FakeCurl()
    _, _, _, q, _, _, control = _set_stream_options(curl, asyncio.Queue, asyncio.Event)
    write = curl.options[CurlOpt.WRITEFUNCTION]

    assert q.maxsize == 1
    assert write(b"first") == len(b"first")
    assert write(b"second") == CURL_WRITEFUNC_PAUSE
    assert q.get_nowait() == b"first"

    control.resume()
    assert curl.pause_calls == [CURLPAUSE_CONT]
    assert write(b"second") == len(b"second")


def test_stream_queue_size_must_be_positive():
    curl = FakeCurl()

    with pytest.raises(ValueError, match="stream_queue_size"):
        utils.set_curl_options(
            curl,
            "GET",
            "https://example.com/",
            params_list=[None, None],
            headers_list=[None, None],
            cookies_list=[None, None],
            proxies_list=[None, None],
            verify_list=[True, None],
            stream=True,
            stream_queue_size=0,
            queue_class=queue.Queue,
            event_class=threading.Event,
        )


def test_set_curl_options_routes_perk_to_perk_options(monkeypatch):
    curl = FakeCurl()
    perk = "1:2|m,a,s,p|3:4"
    set_perk_options = Mock()
    set_akamai_options = Mock()

    monkeypatch.setattr(utils, "set_perk_options", set_perk_options)
    monkeypatch.setattr(utils, "set_akamai_options", set_akamai_options)

    utils.set_curl_options(
        curl,
        "GET",
        "https://example.com/",
        params_list=[None, None],
        headers_list=[None, None],
        cookies_list=[None, None],
        proxies_list=[None, None],
        verify_list=[True, None],
        perk=perk,
    )

    set_perk_options.assert_called_once_with(curl, perk)
    set_akamai_options.assert_not_called()


def test_set_ja3_options_sets_tls_options(monkeypatch):
    curl = FakeCurl()
    ja3 = "771,4865-4866,0-11-10,29-23,0"
    toggle_extensions_by_ids = Mock()

    monkeypatch.setattr(
        utils,
        "toggle_extensions_by_ids",
        toggle_extensions_by_ids,
    )

    utils.set_ja3_options(curl, ja3)

    assert curl.options[CurlOpt.SSLVERSION] == (
        CurlSslVersion.TLSv1_2 | CurlSslVersion.MAX_DEFAULT
    )
    assert curl.options[CurlOpt.SSL_CIPHER_LIST] == (
        "TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384"
    )
    toggle_extensions_by_ids.assert_called_once_with(curl, {0, 10, 11})
    assert curl.options[CurlOpt.TLS_EXTENSION_ORDER] == "0-11-10"
    assert curl.options[CurlOpt.SSL_EC_CURVES] == "X25519:P-256"


def test_set_ja3_options_with_permutation_skips_extension_order(monkeypatch):
    curl = FakeCurl()

    monkeypatch.setattr(utils, "toggle_extensions_by_ids", Mock())

    utils.set_ja3_options(
        curl,
        "771,4865-4866,0-11-10,29-23,0",
        permute=True,
    )

    assert CurlOpt.TLS_EXTENSION_ORDER not in curl.options


def test_set_akamai_options_sets_http2_options():
    curl = FakeCurl()

    utils.set_akamai_options(curl, "1:65536,2:0|15663105|0|m,a,s,p")

    assert curl.options[CurlOpt.HTTP_VERSION] == CurlHttpVersion.V2_0
    assert curl.options[CurlOpt.HTTP2_SETTINGS] == "1:65536;2:0"
    assert curl.options[CurlOpt.HTTP2_WINDOW_UPDATE] == 15663105
    assert CurlOpt.HTTP2_STREAMS not in curl.options
    assert curl.options[CurlOpt.HTTP2_PSEUDO_HEADERS_ORDER] == "masp"


def test_set_akamai_options_sets_nonzero_streams():
    curl = FakeCurl()

    utils.set_akamai_options(curl, "1:65536|15663105|1:0:0:201|m,a,s,p")

    assert curl.options[CurlOpt.HTTP2_STREAMS] == "1:0:0:201"


def test_set_perk_options_sets_http3_options():
    curl = FakeCurl()

    utils.set_perk_options(curl, "1:2|m,a,s,p|3:4")

    assert curl.options[CurlOpt.HTTP3_SETTINGS] == "1:2"
    assert curl.options[CurlOpt.HTTP3_PSEUDO_HEADERS_ORDER] == "masp"
    assert curl.options[CurlOpt.QUIC_TRANSPORT_PARAMETERS] == "3:4"


def test_set_extra_fp_sets_extra_fingerprint_options():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(
        tls_signature_algorithms=["rsa_pss_rsae_sha256", "ecdsa_secp256r1_sha256"],
        tls_min_version=CurlSslVersion.TLSv1_3,
        tls_grease=True,
        tls_permute_extensions=True,
        tls_cert_compression="zlib",
        tls_delegated_credential="ecdsa_secp256r1_sha256",
        tls_record_size_limit=4001,
        http2_stream_weight=128,
        http2_stream_exclusive=0,
        http2_no_priority=True,
        header_order="user-agent,accept",
        split_cookies=True,
        form_boundary=True,
        http3_sig_hash_algs="rsa_pss_rsae_sha256",
        http3_tls_extension_order="0-10-13",
    )

    utils.set_extra_fp(curl, extra_fp)

    assert curl.options[CurlOpt.SSL_SIG_HASH_ALGS] == (
        "rsa_pss_rsae_sha256,ecdsa_secp256r1_sha256"
    )
    assert curl.options[CurlOpt.SSLVERSION] == (
        CurlSslVersion.TLSv1_3 | CurlSslVersion.MAX_DEFAULT
    )
    assert curl.options[CurlOpt.TLS_GREASE] == 1
    assert curl.options[CurlOpt.SSL_PERMUTE_EXTENSIONS] == 1
    assert curl.options[CurlOpt.SSL_CERT_COMPRESSION] == "zlib"
    assert curl.options[CurlOpt.TLS_DELEGATED_CREDENTIALS] == ("ecdsa_secp256r1_sha256")
    assert curl.options[CurlOpt.TLS_RECORD_SIZE_LIMIT] == 4001
    assert curl.options[CurlOpt.STREAM_WEIGHT] == 128
    assert curl.options[CurlOpt.STREAM_EXCLUSIVE] == 0
    assert curl.options[CurlOpt.HTTP2_NO_PRIORITY] is True
    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "user-agent,accept"
    assert curl.options[CurlOpt.SPLIT_COOKIES] is True
    assert curl.options[CurlOpt.FORM_BOUNDARY] is True
    assert curl.options[CurlOpt.HTTP3_SIG_HASH_ALGS] == "rsa_pss_rsae_sha256"
    assert curl.options[CurlOpt.HTTP3_TLS_EXTENSION_ORDER] == "0-10-13"


def test_set_extra_fp_skips_unset_profile_defaults():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(tls_permute_extensions=True)

    utils.set_extra_fp(curl, extra_fp)

    assert curl.options == {CurlOpt.SSL_PERMUTE_EXTENSIONS: 1}


def test_set_extra_fp_honors_explicit_false_and_zero_values():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(
        tls_grease=False,
        tls_permute_extensions=False,
        http2_stream_exclusive=0,
    )

    utils.set_extra_fp(curl, extra_fp)

    assert curl.options[CurlOpt.TLS_GREASE] == 0
    assert curl.options[CurlOpt.SSL_PERMUTE_EXTENSIONS] == 0
    assert curl.options[CurlOpt.STREAM_EXCLUSIVE] == 0


def _set_interface(interface):
    curl = FakeCurl()
    utils.set_curl_options(
        curl,
        "GET",
        "https://example.com/",
        params_list=[None, None],
        headers_list=[None, None],
        cookies_list=[None, None],
        proxies_list=[None, None],
        verify_list=[True, None],
        interface=interface,
    )
    return curl


@pytest.mark.parametrize(
    "interface,expected",
    [
        ("192.0.2.10", b"host!192.0.2.10"),
        ("2001:db8::1", b"host!2001:db8::1"),
    ],
)
def test_interface_bare_ip_gets_host_prefix(interface, expected):
    curl = _set_interface(interface)

    assert curl.options[CurlOpt.INTERFACE] == expected


@pytest.mark.parametrize("interface", ["eth0", "host!192.0.2.10"])
def test_interface_name_and_prefixed_values_pass_through(interface):
    curl = _set_interface(interface)

    assert curl.options[CurlOpt.INTERFACE] == interface.encode()
