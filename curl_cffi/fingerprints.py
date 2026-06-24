import json
import os
import warnings
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from io import BytesIO
from typing import Literal
from urllib.parse import urlencode

from .const import CurlInfo, CurlOpt
from .curl import Curl, CurlError
from .utils import CurlCffiWarning

__all__ = [
    "Fingerprint",
    "FingerprintUpdateError",
    "FingerprintSpec",
    "FingerprintManager",
    "get_fingerprint",
]

FINGERPRINT_PAGE_LIMIT = 100
FINGERPRINT_CACHE_VERSION = 2
FINGERPRINT_METADATA_FIELDS = {
    "source",
    "http2_source_id",
    "http3_source_id",
}


"""
config example
{
    "api_key": "imp_xxxxxx",
    "updated_at": "2025-08-26 18:01:01"
}
"""

NATIVE_IMPERSONATE_TARGETS = [
    {
        "browser": "Chrome",
        "version": "99",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome99",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "100",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome100",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "101",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome101",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "104",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome104",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "107",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome107",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "110",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome110",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "116",
        "os": "Windows",
        "os_version": "10",
        "target_name": "chrome116",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "119",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "chrome119",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "120",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "chrome120",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "123",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "chrome123",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "124",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "chrome124",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "131",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "chrome131",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "133",
        "os": "macOS",
        "os_version": "Sequoia",
        "target_name": "chrome133a",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "136",
        "os": "macOS",
        "os_version": "Sequoia",
        "target_name": "chrome136",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "142",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "chrome142",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "145",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "chrome145",
        "h3_fingerprints": True,
    },
    {
        "browser": "Chrome",
        "version": "146",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "chrome146",
        "h3_fingerprints": True,
    },
    {
        "browser": "Chrome",
        "version": "99",
        "os": "Android",
        "os_version": "12",
        "target_name": "chrome99_android",
        "h3_fingerprints": False,
    },
    {
        "browser": "Chrome",
        "version": "131",
        "os": "Android",
        "os_version": "14",
        "target_name": "chrome131_android",
        "h3_fingerprints": False,
    },
    {
        "browser": "Edge",
        "version": "99",
        "os": "Windows",
        "os_version": "10",
        "target_name": "edge99",
        "h3_fingerprints": False,
    },
    {
        "browser": "Edge",
        "version": "101",
        "os": "Windows",
        "os_version": "10",
        "target_name": "edge101",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "15.3",
        "os": "macOS",
        "os_version": "Big Sur",
        "target_name": "safari153",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "15.5",
        "os": "macOS",
        "os_version": "Monterey",
        "target_name": "safari155",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "17.0",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "safari170",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "17.2",
        "os": "iOS",
        "os_version": "17.2",
        "target_name": "safari172_ios",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "18.0",
        "os": "macOS",
        "os_version": "Sequoia",
        "target_name": "safari180",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "18.0",
        "os": "iOS",
        "os_version": "18.0",
        "target_name": "safari180_ios",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "18.4",
        "os": "macOS",
        "os_version": "Sequoia",
        "target_name": "safari184",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "18.4",
        "os": "iOS",
        "os_version": "18.4",
        "target_name": "safari184_ios",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "26.0",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "safari260",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "26.0.1",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "safari2601",
        "h3_fingerprints": False,
    },
    {
        "browser": "Safari",
        "version": "26.0",
        "os": "iOS",
        "os_version": "26.0",
        "target_name": "safari260_ios",
        "h3_fingerprints": False,
    },
    {
        "browser": "Firefox",
        "version": "133.0",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "firefox133",
        "h3_fingerprints": False,
    },
    {
        "browser": "Firefox",
        "version": "135.0",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "firefox135",
        "h3_fingerprints": False,
    },
    {
        "browser": "Firefox",
        "version": "144.0",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "firefox144",
        "h3_fingerprints": False,
    },
    {
        "browser": "Firefox",
        "version": "147.0",
        "os": "macOS",
        "os_version": "Tahoe",
        "target_name": "firefox147",
        "h3_fingerprints": True,
    },
    {
        "browser": "Tor",
        "version": "14.5",
        "os": "macOS",
        "os_version": "Sonoma",
        "target_name": "tor145",
        "h3_fingerprints": False,
    },
]


API_ROOT_V1 = "https://api.impersonate.pro/v1"
API_ROOT_V2 = "https://api.impersonate.pro/v2"
DEFAULT_API_ROOT = API_ROOT_V2


class FingerprintUpdateError(RuntimeError, CurlError):
    """Raised when fingerprint update fails."""


def _get_default_config_dir() -> str:
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return os.path.join(appdata, "impersonate")
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return os.path.join(userprofile, "AppData", "Roaming", "impersonate")
        home = os.path.expanduser("~")
        return os.path.join(home, "AppData", "Roaming", "impersonate")

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return os.path.join(xdg_config_home, "impersonate")
    return os.path.expanduser("~/.config/impersonate")


@dataclass
class TlsFingerprint:
    version: str = ""
    ciphers: list[str] = field(default_factory=list)
    alpn: bool = False
    alps: bool = False
    cert_compression: list[str] = field(default_factory=list)
    session_ticket: bool = False
    extension_order: str = ""
    delegated_credentials: list[str] = field(default_factory=list)
    record_size_limit: int | None = None
    grease: bool = False
    use_new_alps_codepoint: bool = False
    signed_cert_timestamps: bool = False
    ech: str | None = None
    permute_extensions: bool = False
    signature_hashes: list[str] = field(default_factory=list)
    supported_groups: list[str] = field(default_factory=list)
    key_shares_limit: int | None = None


@dataclass
class Http2Fingerprint:
    tls: TlsFingerprint = field(default_factory=TlsFingerprint)
    settings: str = ""
    pseudo_headers_order: str = ""
    header_order: list[str] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    header_lang: str = ""
    window_update: int = 0
    stream_weight: int | None = None
    stream_exclusive: int | None = None
    no_priority: bool = False
    priority_weight: int | None = None
    priority_exclusive: int | None = None
    split_cookies: bool = False
    form_boundary: str = ""

    def __post_init__(self):
        if isinstance(self.tls, dict):
            self.tls = TlsFingerprint(**self.tls)


@dataclass
class Http3Fingerprint:
    tls: TlsFingerprint = field(default_factory=TlsFingerprint)
    settings: str = ""
    pseudo_headers_order: str = ""
    header_order: list[str] = field(default_factory=list)
    headers: list[dict[str, str]] = field(default_factory=list)
    header_lang: str = ""
    quic_transport_parameters: str = ""
    split_cookies: bool = False
    form_boundary: str = ""

    def __post_init__(self):
        if isinstance(self.tls, dict):
            self.tls = TlsFingerprint(**self.tls)


LEGACY_FINGERPRINT_FIELDS = {
    "tls_version",
    "tls_ciphers",
    "tls_alpn",
    "tls_alps",
    "tls_cert_compression",
    "tls_signature_hashes",
    "tls_key_shares_limit",
    "tls_supported_groups",
    "tls_session_ticket",
    "tls_extension_order",
    "tls_delegated_credentials",
    "tls_record_size_limit",
    "tls_grease",
    "tls_use_new_alps_codepoint",
    "tls_signed_cert_timestamps",
    "tls_ech",
    "tls_permute_extensions",
    "headers",
    "header_order",
    "split_cookies",
    "form_boundary",
    "http2_settings",
    "http2_window_update",
    "http2_pseudo_headers_order",
    "http2_stream_weight",
    "http2_stream_exclusive",
    "http2_no_priority",
    "http3_settings",
    "http3_pseudo_headers_order",
    "http3_sig_hash_algs",
    "http3_tls_extension_order",
    "quic_transport_parameters",
    "header_lang",
}


_MISSING = object()


def _identity(value):
    return value


def _headers_to_v2(headers):
    if isinstance(headers, dict):
        return [{"name": name, "value": value} for name, value in headers.items()]
    return headers


def _headers_to_v1(headers):
    return {header["name"]: header["value"] for header in headers}


def _sig_hash_algs_to_signature_hashes(value):
    if isinstance(value, str):
        return value.split(",") if value else []
    return value


def _signature_hashes_to_sig_hash_algs(value):
    return ",".join(value)


def _set_if_present(
    target: object,
    attr: str,
    legacy: dict[str, object],
    key: str,
    transform=_identity,
) -> None:
    value = legacy.get(key)
    if not getattr(target, attr) and value:
        setattr(target, attr, transform(value))


def _set_if_none(
    target: object,
    attr: str,
    legacy: dict[str, object],
    key: str,
    transform=_identity,
) -> None:
    value = legacy.get(key)
    if getattr(target, attr) is None and value is not None:
        setattr(target, attr, transform(value))


def _legacy_field_proxy(
    path: str,
    none_default: object = _MISSING,
    getter_transform=_identity,
    setter_transform=_identity,
) -> property:
    attrs = path.split(".")

    def warn():
        warnings.warn(
            (
                "The legacy flat Fingerprint field is deprecated; "
                f"use `fingerprint.{path}` instead."
            ),
            CurlCffiWarning,
            stacklevel=3,
        )

    def getter(self):
        warn()
        value = self
        for attr in attrs:
            value = getattr(value, attr)
        if value is None and none_default is not _MISSING:
            return none_default
        return getter_transform(value)

    def setter(self, value):
        warn()
        target = self
        for attr in attrs[:-1]:
            target = getattr(target, attr)
        setattr(target, attrs[-1], setter_transform(value))

    return property(getter, setter)


@dataclass(init=False)
class Fingerprint:
    client: str = ""
    client_version: str = ""
    os: str = ""
    os_version: str = ""
    http2: Http2Fingerprint = field(default_factory=Http2Fingerprint)
    http3: Http3Fingerprint = field(default_factory=Http3Fingerprint)

    def __init__(
        self,
        client: str = "",
        client_version: str = "",
        os: str = "",
        os_version: str = "",
        http2: Http2Fingerprint | dict[str, object] | None = None,
        http3: Http3Fingerprint | dict[str, object] | None = None,
        **legacy: object,
    ):
        unexpected = set(legacy) - LEGACY_FINGERPRINT_FIELDS
        if unexpected:
            unexpected_args = ", ".join(sorted(unexpected))
            raise TypeError(f"Unexpected fingerprint field(s): {unexpected_args}")

        self.client = client
        self.client_version = client_version
        self.os = os
        self.os_version = os_version
        self.http2 = self._coerce_http2(http2)
        self.http3 = self._coerce_http3(http3)
        self._apply_legacy_fields(legacy)

    @staticmethod
    def _filter_input_dict(value: dict[str, object]) -> dict[str, object]:
        allowed = {
            "client",
            "client_version",
            "os",
            "os_version",
            "http2",
            "http3",
            *LEGACY_FINGERPRINT_FIELDS,
        }
        return {key: item for key, item in value.items() if key in allowed}

    @staticmethod
    def _coerce_http2(
        value: Http2Fingerprint | dict[str, object] | None,
    ) -> Http2Fingerprint:
        if value is None:
            return Http2Fingerprint()
        if isinstance(value, dict):
            return Http2Fingerprint(**value)
        return value

    @staticmethod
    def _coerce_http3(
        value: Http3Fingerprint | dict[str, object] | None,
    ) -> Http3Fingerprint:
        if value is None:
            return Http3Fingerprint()
        if isinstance(value, dict):
            return Http3Fingerprint(**value)
        return value

    def _apply_legacy_fields(self, legacy: dict[str, object]) -> None:
        for http in (self.http2, self.http3):
            tls = http.tls
            _set_if_present(tls, "version", legacy, "tls_version")
            _set_if_present(tls, "ciphers", legacy, "tls_ciphers", list)
            _set_if_present(tls, "alpn", legacy, "tls_alpn", bool)
            _set_if_present(tls, "alps", legacy, "tls_alps", bool)
            _set_if_present(
                tls, "cert_compression", legacy, "tls_cert_compression", list
            )
            _set_if_present(tls, "session_ticket", legacy, "tls_session_ticket", bool)
            _set_if_present(
                tls, "signature_hashes", legacy, "tls_signature_hashes", list
            )
            _set_if_present(
                tls, "supported_groups", legacy, "tls_supported_groups", list
            )
            _set_if_none(tls, "key_shares_limit", legacy, "tls_key_shares_limit")
            _set_if_present(
                tls, "delegated_credentials", legacy, "tls_delegated_credentials", list
            )
            _set_if_none(tls, "record_size_limit", legacy, "tls_record_size_limit")
            _set_if_present(tls, "grease", legacy, "tls_grease", bool)
            _set_if_present(
                tls,
                "use_new_alps_codepoint",
                legacy,
                "tls_use_new_alps_codepoint",
                bool,
            )
            _set_if_present(
                tls,
                "signed_cert_timestamps",
                legacy,
                "tls_signed_cert_timestamps",
                bool,
            )
            _set_if_none(tls, "ech", legacy, "tls_ech")
            _set_if_present(
                tls, "permute_extensions", legacy, "tls_permute_extensions", bool
            )
            _set_if_present(http, "headers", legacy, "headers", _headers_to_v2)
            _set_if_present(http, "header_order", legacy, "header_order")
            _set_if_present(http, "header_lang", legacy, "header_lang")

        _set_if_present(
            self.http2.tls, "extension_order", legacy, "tls_extension_order"
        )
        _set_if_present(self.http2, "settings", legacy, "http2_settings")
        _set_if_present(
            self.http2,
            "pseudo_headers_order",
            legacy,
            "http2_pseudo_headers_order",
        )
        _set_if_present(self.http2, "window_update", legacy, "http2_window_update")
        _set_if_none(self.http2, "stream_weight", legacy, "http2_stream_weight")
        _set_if_none(self.http2, "stream_exclusive", legacy, "http2_stream_exclusive")
        _set_if_present(self.http2, "no_priority", legacy, "http2_no_priority", bool)
        _set_if_present(self.http2, "split_cookies", legacy, "split_cookies", bool)
        _set_if_present(self.http2, "form_boundary", legacy, "form_boundary")

        _set_if_present(
            self.http3.tls,
            "extension_order",
            legacy,
            "http3_tls_extension_order",
        )
        _set_if_present(
            self.http3.tls,
            "signature_hashes",
            legacy,
            "http3_sig_hash_algs",
            _sig_hash_algs_to_signature_hashes,
        )
        _set_if_present(self.http3, "settings", legacy, "http3_settings")
        _set_if_present(
            self.http3,
            "pseudo_headers_order",
            legacy,
            "http3_pseudo_headers_order",
        )
        _set_if_present(
            self.http3,
            "quic_transport_parameters",
            legacy,
            "quic_transport_parameters",
        )

    tls_version = _legacy_field_proxy("http2.tls.version")
    tls_ciphers = _legacy_field_proxy("http2.tls.ciphers")
    tls_alpn = _legacy_field_proxy("http2.tls.alpn")
    tls_alps = _legacy_field_proxy("http2.tls.alps")
    tls_cert_compression = _legacy_field_proxy("http2.tls.cert_compression")
    tls_signature_hashes = _legacy_field_proxy("http2.tls.signature_hashes")
    tls_key_shares_limit = _legacy_field_proxy("http2.tls.key_shares_limit", 0)
    tls_supported_groups = _legacy_field_proxy("http2.tls.supported_groups")
    tls_session_ticket = _legacy_field_proxy("http2.tls.session_ticket")
    tls_extension_order = _legacy_field_proxy("http2.tls.extension_order")
    tls_delegated_credentials = _legacy_field_proxy("http2.tls.delegated_credentials")
    tls_record_size_limit = _legacy_field_proxy("http2.tls.record_size_limit")
    tls_grease = _legacy_field_proxy("http2.tls.grease")
    tls_use_new_alps_codepoint = _legacy_field_proxy("http2.tls.use_new_alps_codepoint")
    tls_signed_cert_timestamps = _legacy_field_proxy("http2.tls.signed_cert_timestamps")
    tls_ech = _legacy_field_proxy("http2.tls.ech")
    tls_permute_extensions = _legacy_field_proxy("http2.tls.permute_extensions")
    headers = _legacy_field_proxy(
        "http2.headers",
        getter_transform=_headers_to_v1,
        setter_transform=_headers_to_v2,
    )
    header_order = _legacy_field_proxy("http2.header_order")
    header_lang = _legacy_field_proxy("http2.header_lang")
    split_cookies = _legacy_field_proxy("http2.split_cookies")
    form_boundary = _legacy_field_proxy("http2.form_boundary")
    http2_settings = _legacy_field_proxy("http2.settings")
    http2_window_update = _legacy_field_proxy("http2.window_update")
    http2_pseudo_headers_order = _legacy_field_proxy("http2.pseudo_headers_order")
    http2_stream_weight = _legacy_field_proxy("http2.stream_weight")
    http2_stream_exclusive = _legacy_field_proxy("http2.stream_exclusive")
    http2_no_priority = _legacy_field_proxy("http2.no_priority")
    http3_settings = _legacy_field_proxy("http3.settings")
    http3_pseudo_headers_order = _legacy_field_proxy("http3.pseudo_headers_order")
    http3_sig_hash_algs = _legacy_field_proxy(
        "http3.tls.signature_hashes",
        getter_transform=_signature_hashes_to_sig_hash_algs,
        setter_transform=_sig_hash_algs_to_signature_hashes,
    )
    http3_tls_extension_order = _legacy_field_proxy("http3.tls.extension_order")
    quic_transport_parameters = _legacy_field_proxy("http3.quic_transport_parameters")


# fmt: off
ClientLiteral = Literal[
    # browsers
    "chrome", "firefox", "edge", "brave", "opera", "brave", "operamini",
    "qihoo", "qq", "quark", "samsung", "sogou", "sogou_ie",
    # http client
    "volley", "okhttp", "webview",
    # app with general web view
    "baidu", "wechat", "bing", "duckduckgo", "google", "yandex",
]
# fmt: on
PlatformLiteral = ["macos", "windows", "linux", "ios", "android"]


@dataclass
class FingerprintSpec:
    platform: str | None = None
    client: ClientLiteral | None = None
    strategy: Literal["uniform"] | None = "uniform"


class FingerprintManager:
    @classmethod
    def get_config_dir(cls) -> str:
        return os.environ.get("IMPERSONATE_CONFIG_DIR", _get_default_config_dir())

    @classmethod
    def get_config_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "config.json")

    @classmethod
    def get_fingerprint_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "fingerprints.json")

    @classmethod
    def get_fingerprint_v2_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "fingerprints_v2.json")

    @staticmethod
    def _is_v2_api_root(api_root: str) -> bool:
        return api_root.rstrip("/").endswith("/v2")

    @staticmethod
    def _normalize_api_version(version: str) -> str:
        version = version.strip().lower()
        if version not in {"v1", "v2"}:
            raise ValueError("IMPERSONATE_API_VERSION must be v1 or v2")
        return version

    @classmethod
    def get_api_root(cls) -> str:
        api_root = os.environ.get("IMPERSONATE_API_ROOT")
        if api_root:
            return api_root

        api_version = os.environ.get("IMPERSONATE_API_VERSION")
        if api_version:
            version = cls._normalize_api_version(api_version)
            return API_ROOT_V1 if version == "v1" else API_ROOT_V2

        return DEFAULT_API_ROOT

    @classmethod
    def get_api_key(cls) -> str | None:
        api_key = os.environ.get("IMPERSONATE_API_KEY")
        if api_key:
            return api_key
        config_path = cls.get_config_path()
        if not os.path.exists(config_path):
            return None
        with open(config_path) as f:
            try:
                config = json.load(f)
            except json.JSONDecodeError:
                return None
        api_key = config.get("api_key")
        if isinstance(api_key, str) and api_key:
            return api_key
        return None

    @classmethod
    def set_api_key(cls, api_key: str) -> None:
        """Persist the API key for impersonate.pro."""
        config_dir = cls.get_config_dir()
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        config_file = cls.get_config_path()
        if os.path.exists(config_file):
            with open(config_file) as f:
                try:
                    config = json.load(f)
                except json.JSONDecodeError:
                    config = {}
        else:
            config = {}
        config["api_key"] = api_key
        config["update_time"] = datetime.utcnow().isoformat()
        with open(config_file, "w") as f:
            json.dump(config, f, indent=4)

    @staticmethod
    def _fetch_fingerprint_payload(url: str, headers: dict[str, str]) -> bytes:
        curl = Curl()
        buffer = BytesIO()
        try:
            curl.setopt(CurlOpt.URL, url.encode())
            if headers:
                curl.setopt(
                    CurlOpt.HTTPHEADER,
                    [f"{key}: {value}".encode() for key, value in headers.items()],
                )
            curl.setopt(CurlOpt.WRITEDATA, buffer)
            curl.perform()
            status_code = int(curl.getinfo(CurlInfo.RESPONSE_CODE))
        except CurlError as exc:
            raise FingerprintUpdateError(
                f"Failed to access fingerprint endpoint at {url}: {exc}"
            ) from exc
        finally:
            curl.close()

        payload = buffer.getvalue()
        if status_code >= 400:
            body = payload.decode("utf-8", errors="replace")
            raise FingerprintUpdateError(
                f"Failed to access fingerprint endpoint at {url}: "
                f"HTTP {status_code}: {body}"
            )
        return payload

    @classmethod
    def update_fingerprints(cls, api_root: str | None = None) -> int:
        """Get the latest fingerprints for impersonating."""
        api_root = api_root or cls.get_api_root()
        base_url = f"{api_root.rstrip('/')}/fingerprints"
        headers = {}
        api_key = cls.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        fingerprints: dict[str, dict] = {}
        skip = 0
        limit = FINGERPRINT_PAGE_LIMIT
        while True:
            url = f"{base_url}?{urlencode({'skip': skip, 'limit': limit})}"
            payload = cls._fetch_fingerprint_payload(url, headers)

            try:
                data = json.loads(payload)
                if not isinstance(data, dict):
                    raise FingerprintUpdateError(
                        f"Invalid fingerprint response from {url}: expected object"
                    )
                items = data.get("items", data.get("data"))
            except json.JSONDecodeError as exc:
                raise FingerprintUpdateError(
                    f"Invalid fingerprint response from {url}: {exc}"
                ) from exc

            if not isinstance(items, list):
                raise FingerprintUpdateError(f"No fingerprints found at {url}")

            for item in items:
                if not isinstance(item, dict):
                    continue
                name = item.get("name") or item.get("target")
                if not name:
                    continue
                raw = item.get("data", item.get("fingerprint", {}))
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                if isinstance(raw, dict):
                    raw = raw.copy()
                    if "client" not in raw and isinstance(item.get("client"), str):
                        raw["client"] = item["client"]
                    if "client_version" not in raw and isinstance(
                        item.get("version"), str
                    ):
                        raw["client_version"] = item["version"]
                    if "os" not in raw and isinstance(item.get("os"), str):
                        raw["os"] = item["os"]
                    if "os_version" not in raw and isinstance(
                        item.get("os_version"), str
                    ):
                        raw["os_version"] = item["os_version"]
                    for key in FINGERPRINT_METADATA_FIELDS:
                        if key not in raw and isinstance(item.get(key), str):
                            raw[key] = item[key]
                    fingerprints[name] = raw

            pagination = data.get("pagination")
            if not isinstance(pagination, dict) or not pagination.get("has_more"):
                break
            next_skip = pagination.get("next_skip")
            if not isinstance(next_skip, int) or next_skip <= skip:
                raise FingerprintUpdateError(
                    f"Invalid fingerprint pagination from {url}: "
                    "expected increasing next_skip"
                )
            skip = next_skip

        config_dir = cls.get_config_dir()
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        fingerprint_path = (
            cls.get_fingerprint_v2_path()
            if cls._is_v2_api_root(api_root)
            else cls.get_fingerprint_path()
        )
        with open(fingerprint_path, "w") as wf:
            json.dump(
                {"version": FINGERPRINT_CACHE_VERSION, "data": fingerprints},
                wf,
                indent=2,
            )
        cls.load_fingerprints.cache_clear()
        return len(fingerprints)

    @staticmethod
    def _unwrap_fingerprint_cache(payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            return {}
        version = payload.get("version")
        data = payload.get("data")
        if version == FINGERPRINT_CACHE_VERSION and isinstance(data, dict):
            return data
        return payload

    @staticmethod
    def _parse_fingerprints(payload: dict[str, object]) -> dict[str, Fingerprint]:
        parsed: dict[str, Fingerprint] = {}
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            parsed[key] = Fingerprint(**Fingerprint._filter_input_dict(value))
        return parsed

    @classmethod
    def _load_native_fingerprints(cls) -> dict[str, Fingerprint]:
        native_payload: dict[str, dict[str, str]] = {}
        for item in NATIVE_IMPERSONATE_TARGETS:
            target_name = item.get("target_name")
            if not isinstance(target_name, str) or not target_name:
                continue
            browser = item.get("browser")
            version = item.get("version")
            os_name = item.get("os")
            os_version = item.get("os_version")
            native_payload[target_name] = {
                "client": browser.lower() if isinstance(browser, str) else "",
                "client_version": version if isinstance(version, str) else "",
                "os": os_name if isinstance(os_name, str) else "",
                "os_version": os_version if isinstance(os_version, str) else "",
            }
        return cls._parse_fingerprints(native_payload)

    @classmethod
    @cache
    def load_fingerprints(cls) -> dict[str, Fingerprint]:
        parsed = cls._load_native_fingerprints()
        v2_path = cls.get_fingerprint_v2_path()
        fingerprint_path = (
            v2_path if os.path.exists(v2_path) else cls.get_fingerprint_path()
        )
        if os.path.exists(fingerprint_path):
            with open(fingerprint_path) as f:
                fingerprints = json.loads(f.read())
            fingerprints = cls._unwrap_fingerprint_cache(fingerprints)
            parsed.update(cls._parse_fingerprints(fingerprints))
        return parsed

    @classmethod
    def get_fingerprint(cls, target: str) -> Fingerprint:
        """Return a deep-copied fingerprint that callers can edit safely."""
        fingerprints = cls.load_fingerprints()
        if target not in fingerprints:
            raise KeyError(f"Fingerprint target not found: {target}")
        return deepcopy(fingerprints[target])

    @classmethod
    def list_fingerprints(cls) -> list[dict[str, object]]:
        native_lookup = {
            item["target_name"]: item for item in NATIVE_IMPERSONATE_TARGETS
        }
        rows: list[dict[str, object]] = []
        for name, fingerprint in sorted(cls.load_fingerprints().items()):
            native = native_lookup.get(name)
            if native:
                rows.append(
                    {
                        "type": "builtin",
                        "name": name,
                        "browser": native.get("browser", ""),
                        "version": native.get("version", ""),
                        "os": native.get("os", ""),
                        "os_version": native.get("os_version", ""),
                        "h3_fingerprints": bool(native.get("h3_fingerprints", False)),
                    }
                )
            else:
                rows.append(
                    {
                        "type": "custom",
                        "name": name,
                        "browser": fingerprint.client,
                        "version": fingerprint.client_version,
                        "os": fingerprint.os,
                        "os_version": fingerprint.os_version,
                        "h3_fingerprints": bool(
                            fingerprint.http3.settings
                            or fingerprint.http3.pseudo_headers_order
                            or fingerprint.http3.quic_transport_parameters
                        ),
                    }
                )
        return rows


def get_fingerprint(target: str) -> Fingerprint:
    """Return a deep-copied fingerprint that callers can edit safely."""
    return FingerprintManager.get_fingerprint(target)
