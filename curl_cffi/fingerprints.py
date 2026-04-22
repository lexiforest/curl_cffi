import json
import os
from copy import deepcopy
from dataclasses import dataclass, field, fields
from datetime import datetime
from functools import cache
from io import BytesIO
from typing import Literal

from .const import CurlInfo, CurlOpt
from .curl import Curl, CurlError

__all__ = [
    "Fingerprint",
    "FingerprintUpdateError",
    "FingerprintSpec",
    "FingerprintManager",
    "get_fingerprint",
]


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


DEFAULT_API_ROOT = "https://api.impersonate.pro/v1"


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
class Fingerprint:
    client: str = ""
    client_version: str = ""
    os: str = ""
    os_version: str = ""

    http_version: str = "v2"

    tls_version: str = "1.2"
    tls_ciphers: list[str] = field(default_factory=list)
    # the value is [h2, http/1.1], which will be filled by libcurl
    tls_alpn: bool = False
    tls_alps: bool = False
    tls_cert_compression: list[str] = field(default_factory=list)
    tls_signature_hashes: list[str] = field(default_factory=list)  # .sig_hash_args
    tls_key_shares_limit: int = 2  # the default key shares length is 2
    tls_supported_groups: list[str] = field(default_factory=list)  # .curves
    tls_session_ticket: bool = False
    tls_extension_order: str = ""
    tls_delegated_credentials: list[str] = field(default_factory=list)
    tls_record_size_limit: int | None = None
    tls_grease: bool = False
    tls_use_new_alps_codepoint: bool = False
    tls_signed_cert_timestamps: bool = False
    tls_ech: str | None = None
    tls_permute_extensions: bool = False

    headers: dict[str, str] = field(default_factory=dict)
    header_order: str = ""
    split_cookies: bool = False
    form_boundary: str = ""

    http2_settings: str = ""
    http2_window_update: int = 0
    http2_pseudo_headers_order: str = ""
    http2_stream_weight: int | None = None
    http2_stream_exclusive: int | None = None
    http2_no_priority: bool = False

    http3_settings: str = ""
    http3_pseudo_headers_order: str = ""
    http3_tls_extension_order: str = ""
    quic_transport_parameters: str = ""

    header_lang: str = ""


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
    def get_api_root(cls) -> str:
        return (
            os.environ.get("IMPERSONATE_API_ROOT", DEFAULT_API_ROOT) or DEFAULT_API_ROOT
        )

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
        url = f"{api_root.rstrip('/')}/fingerprints"
        headers = {}
        api_key = cls.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
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

        fingerprints: dict[str, dict] = {}
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
                fingerprints[name] = raw

        config_dir = cls.get_config_dir()
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(cls.get_fingerprint_path(), "w") as wf:
            json.dump(fingerprints, wf, indent=2)
        cls.load_fingerprints.cache_clear()
        return len(fingerprints)

    @staticmethod
    def _parse_fingerprints(payload: dict[str, object]) -> dict[str, Fingerprint]:
        allowed = {item.name for item in fields(Fingerprint)}
        parsed: dict[str, Fingerprint] = {}
        for key, value in payload.items():
            if not isinstance(value, dict):
                continue
            filtered = {k: v for k, v in value.items() if k in allowed}
            parsed[key] = Fingerprint(**filtered)
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
        fingerprint_path = cls.get_fingerprint_path()
        if os.path.exists(fingerprint_path):
            with open(fingerprint_path) as f:
                fingerprints = json.loads(f.read())
            if isinstance(fingerprints, dict):
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
                        "h3_fingerprints": fingerprint.http_version in ("v3", "v3only"),
                    }
                )
        return rows


def get_fingerprint(target: str) -> Fingerprint:
    """Return a deep-copied fingerprint that callers can edit safely."""
    return FingerprintManager.get_fingerprint(target)
