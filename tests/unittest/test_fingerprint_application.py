from curl_cffi.const import CurlOpt
from curl_cffi.fingerprints import Fingerprint
from curl_cffi.requests.headers import Headers
from curl_cffi.requests.impersonate import ExtraFingerprints
from curl_cffi.requests.utils import DEFAULT_TCP_FINGERPRINTS
from curl_cffi.requests.utils import _apply_fingerprint
from curl_cffi.requests.utils import _resolve_tcp_fp
from curl_cffi.requests.utils import set_extra_fp
from curl_cffi.requests.utils import set_tcp_fp_options


class FakeCurl:
    def __init__(self):
        self.options = {}

    def setopt(self, option, value):
        self.options[option] = value


def test_apply_fingerprint_strips_padding_extension_from_tls_extension_order(
    monkeypatch,
):
    curl = FakeCurl()
    fingerprint = Fingerprint(tls_extension_order="0-21-11")
    seen_extension_ids = None

    def fake_toggle_extensions_by_ids(_curl, extension_ids):
        nonlocal seen_extension_ids
        seen_extension_ids = extension_ids

    monkeypatch.setattr(
        "curl_cffi.requests.utils.toggle_extensions_by_ids",
        fake_toggle_extensions_by_ids,
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert seen_extension_ids == {0, 11}
    assert curl.options[CurlOpt.TLS_EXTENSION_ORDER] == "0-11"


def test_apply_fingerprint_rewrites_kyber_supported_group_alias():
    curl = FakeCurl()
    fingerprint = Fingerprint(tls_supported_groups=["X25519Kyber768", "P-256"])

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.SSL_EC_CURVES] == "X25519Kyber768Draft00:P-256"


def test_apply_fingerprint_with_tls_extension_order_respects_cert_compression():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        tls_extension_order="0-23-65281-10-11-16-5-13-18-51-45-43-27",
        tls_cert_compression=["zlib"],
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=False,
    )

    assert curl.options[CurlOpt.SSL_CERT_COMPRESSION] == "zlib"


def test_apply_fingerprint_empty_host_uses_curl_generated_host():
    curl = FakeCurl()
    fingerprint = Fingerprint(
        headers={
            "User-Agent": "test-agent",
            "Host": "",
            "Connection": "Keep-Alive",
        },
        header_order="User-Agent,Host,Connection",
    )

    _apply_fingerprint(
        curl,
        fingerprint,
        existing_header_names=set(),
        default_headers=True,
    )

    assert curl.options[CurlOpt.HTTPHEADER] == [
        b"User-Agent: test-agent",
        b"Connection: Keep-Alive",
    ]
    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "User-Agent,Host,Connection"


def test_set_extra_fp_sets_header_order():
    curl = FakeCurl()
    extra_fp = ExtraFingerprints(header_order="User-Agent,Host,Connection")

    set_extra_fp(curl, extra_fp)

    assert curl.options[CurlOpt.HTTPHEADER_ORDER] == "User-Agent,Host,Connection"


def test_set_tcp_fp_options_uses_linux_rcvbuf_half_window(monkeypatch):
    import socket

    curl = FakeCurl()
    setsockopt_calls = []

    class FakeSocket:
        def __init__(self, fileno):
            self.fileno = fileno

        def setsockopt(self, level, option, value):
            setsockopt_calls.append((level, option, value))

        def detach(self):
            return self.fileno

    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(socket, "socket", FakeSocket)

    set_tcp_fp_options(curl, "64,29200,7,1460")
    sockopt_cb = curl.options[CurlOpt.SOCKOPTFUNCTION]

    assert sockopt_cb(123, 0) == 0
    assert (socket.SOL_SOCKET, socket.SO_RCVBUF, 14600) in setsockopt_calls
    assert (socket.IPPROTO_TCP, 10, 29200) in setsockopt_calls


def test_resolve_tcp_fp_auto_from_native_impersonate_target():
    tcp_fp = _resolve_tcp_fp("auto", Headers(), "chrome110", None)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["windows"]


def test_resolve_tcp_fp_auto_from_headers_before_impersonate_target():
    headers = Headers(
        {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36"
            )
        }
    )

    tcp_fp = _resolve_tcp_fp("auto", headers, "chrome110", None)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["linux"]


def test_resolve_tcp_fp_auto_from_client_hints_platform():
    headers = Headers({"sec-ch-ua-platform": '"Android"'})

    tcp_fp = _resolve_tcp_fp("auto", headers, None, None)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["android"]


def test_resolve_tcp_fp_auto_from_fingerprint_os():
    fingerprint = Fingerprint(os="macOS")

    tcp_fp = _resolve_tcp_fp("auto", Headers(), None, fingerprint)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["macos"]


def test_resolve_tcp_fp_auto_from_ios_impersonate_target():
    tcp_fp = _resolve_tcp_fp("auto", Headers(), "safari_ios", None)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["ios"]


def test_resolve_tcp_fp_auto_from_ios_user_agent():
    headers = Headers(
        {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.6 "
                "Mobile/15E148 Safari/604.1"
            )
        }
    )

    tcp_fp = _resolve_tcp_fp("auto", headers, None, None)

    assert tcp_fp == DEFAULT_TCP_FINGERPRINTS["ios"]


def test_resolve_tcp_fp_auto_requires_os_signal():
    try:
        _resolve_tcp_fp("auto", Headers(), None, None)
    except ValueError as exc:
        assert 'tcp_fp="auto"' in str(exc)
    else:
        raise AssertionError("Expected ValueError")
