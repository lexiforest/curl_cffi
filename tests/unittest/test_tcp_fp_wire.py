import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass

import pytest

from curl_cffi import requests
from curl_cffi.requests.utils import DEFAULT_TCP_FINGERPRINTS


pytestmark = pytest.mark.skipif(
    sys.platform != "linux",
    reason="wire-level TCP fingerprint tests require Linux raw socket capture",
)


@dataclass(frozen=True)
class TcpFingerprint:
    ttl: int
    window_size: int
    window_scale: int | None
    mss: int | None


class OneShotHttpServer:
    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._error: BaseException | None = None

    @property
    def port(self) -> int:
        return self._sock.getsockname()[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"

    def __enter__(self):
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._sock.close()
        self._thread.join(timeout=2)
        if self._error:
            raise self._error

    def _serve(self) -> None:
        try:
            conn, _addr = self._sock.accept()
            with conn:
                conn.settimeout(2)
                conn.recv(4096)
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\n"
                    b"Content-Length: 2\r\n"
                    b"Connection: close\r\n\r\n"
                    b"OK"
                )
        except BaseException as exc:
            self._error = exc


class TcpSynCapture:
    def __init__(self, dst_port: int, timeout: float = 3.0):
        self.dst_port = dst_port
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._capture, daemon=True)
        self._done = threading.Event()
        self.fingerprint: TcpFingerprint | None = None
        self._error: BaseException | None = None

    def __enter__(self):
        try:
            self._sock = socket.socket(
                socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_TCP
            )
        except PermissionError as exc:
            pytest.skip(f"raw TCP capture requires CAP_NET_RAW/root: {exc}")
        except OSError as exc:
            pytest.skip(f"raw TCP capture is not available: {exc}")

        self._sock.bind(("127.0.0.1", 0))
        self._sock.settimeout(0.1)
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._done.set()
        if self._sock is not None:
            self._sock.close()
        self._thread.join(timeout=1)
        if self._error:
            raise self._error

    def wait(self) -> TcpFingerprint:
        if not self._done.wait(self.timeout):
            pytest.fail("timed out waiting for TCP SYN packet")
        if self.fingerprint is None:
            pytest.fail("TCP SYN capture stopped without a fingerprint")
        return self.fingerprint

    def _capture(self) -> None:
        assert self._sock is not None
        deadline = time.monotonic() + self.timeout
        try:
            while not self._done.is_set() and time.monotonic() < deadline:
                try:
                    packet, _addr = self._sock.recvfrom(65535)
                except TimeoutError:
                    continue
                except OSError:
                    break

                fingerprint = _parse_ipv4_tcp_syn(packet, self.dst_port)
                if fingerprint is not None:
                    self.fingerprint = fingerprint
                    self._done.set()
                    return
        except BaseException as exc:
            self._error = exc
            self._done.set()


def _parse_ipv4_tcp_syn(packet: bytes, dst_port: int) -> TcpFingerprint | None:
    if len(packet) < 40:
        return None
    version = packet[0] >> 4
    if version != 4:
        return None
    ip_header_len = (packet[0] & 0x0F) * 4
    if len(packet) < ip_header_len + 20:
        return None
    protocol = packet[9]
    if protocol != socket.IPPROTO_TCP:
        return None

    tcp = packet[ip_header_len:]
    packet_dst_port = struct.unpack("!H", tcp[2:4])[0]
    if packet_dst_port != dst_port:
        return None
    flags = tcp[13]
    syn = bool(flags & 0x02)
    ack = bool(flags & 0x10)
    if not syn or ack:
        return None

    tcp_header_len = (tcp[12] >> 4) * 4
    options = tcp[20:tcp_header_len]
    return TcpFingerprint(
        ttl=packet[8],
        window_size=struct.unpack("!H", tcp[14:16])[0],
        window_scale=_parse_tcp_option(options, 3),
        mss=_parse_tcp_option(options, 2),
    )


def _parse_tcp_option(options: bytes, kind: int) -> int | None:
    idx = 0
    while idx < len(options):
        option_kind = options[idx]
        if option_kind == 0:
            return None
        if option_kind == 1:
            idx += 1
            continue
        if idx + 1 >= len(options):
            return None
        option_len = options[idx + 1]
        if option_len < 2 or idx + option_len > len(options):
            return None
        option_value = options[idx + 2 : idx + option_len]
        if option_kind == kind:
            if kind == 2 and len(option_value) == 2:
                return struct.unpack("!H", option_value)[0]
            if kind == 3 and len(option_value) == 1:
                return option_value[0]
            return None
        idx += option_len
    return None


def _expected_tcp_fingerprint(tcp_fp: str) -> TcpFingerprint:
    ttl, window_size, window_scale, mss = (int(part) for part in tcp_fp.split(","))
    return TcpFingerprint(ttl, window_size, window_scale, mss)


def _capture_tcp_fingerprint(tcp_fp: str, **request_kwargs) -> TcpFingerprint:
    with OneShotHttpServer() as server, TcpSynCapture(server.port) as capture:
        response = requests.get(server.url, tcp_fp=tcp_fp, timeout=3, **request_kwargs)
        assert response.status_code == 200
        return capture.wait()


@pytest.mark.parametrize(
    "tcp_fp",
    [
        DEFAULT_TCP_FINGERPRINTS["windows"],
        DEFAULT_TCP_FINGERPRINTS["linux"],
        DEFAULT_TCP_FINGERPRINTS["macos"],
        DEFAULT_TCP_FINGERPRINTS["android"],
        DEFAULT_TCP_FINGERPRINTS["ios"],
    ],
)
def test_explicit_tcp_fp_is_sent_on_wire(tcp_fp):
    assert _capture_tcp_fingerprint(tcp_fp) == _expected_tcp_fingerprint(tcp_fp)


def test_auto_tcp_fp_is_sent_on_wire_for_headers():
    captured = _capture_tcp_fingerprint(
        "auto",
        headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
    )

    assert captured == _expected_tcp_fingerprint(DEFAULT_TCP_FINGERPRINTS["linux"])
