import json
import os
from dataclasses import dataclass, field, fields
from datetime import datetime
from functools import cache
from typing import Literal
from urllib.request import Request, urlopen

__all__ = [
    "Fingerprint",
    "FingerprintSpec",
    "FingerprintManager",
]


"""
Pro config example
{
    "api_key": "imp_xxxxxx",
    "updated_at": "2025-08-26 18:01:01"
}
"""


DEFAULT_API_ROOT = "https://api.impersonate.pro/v1"
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.config/impersonate")


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

    headers: dict[str, str] = field(default_factory=dict)

    http2_settings: str = ""
    http2_window_update: int = 0
    http2_pseudo_headers_order: str = ""
    http2_stream_weight: int | None = None
    http2_stream_exclusive: int | None = None
    http2_no_priority: bool = False
    http2_priority_exclusive: int | None = None

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
        return os.environ.get("IMPERSONATE_CONFIG_DIR", DEFAULT_CONFIG_DIR)

    @classmethod
    def get_config_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "config.json")

    @classmethod
    def get_fingerprint_path(cls) -> str:
        return os.path.join(cls.get_config_dir(), "fingerprints.json")

    @classmethod
    def get_api_root(cls) -> str:
        return os.environ.get("IMPERSONATE_API_ROOT", DEFAULT_API_ROOT)

    @classmethod
    def get_api_key(cls) -> str | None:
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
    @cache
    def is_pro(cls) -> bool:
        return cls.get_api_key() is not None

    @classmethod
    def enable_pro(cls, api_key: str) -> None:
        """Enable the pro version."""
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
        cls.is_pro.cache_clear()

    @classmethod
    def update_fingerprints(cls, api_root: str | None = None) -> None:
        """Get the latest fingerprints for impersonating."""
        api_root = api_root or cls.get_api_root()
        url = f"{api_root.rstrip('/')}/fingerprints"
        headers = {}
        api_key = cls.get_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(url, headers=headers, method="GET")
        with urlopen(request) as response:
            data = json.loads(response.read())
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("Fingerprints API returned unexpected payload.")

        fingerprints: dict[str, dict] = {}
        for item in items:
            name = item.get("name") or item.get("target")
            if not name:
                continue
            raw = item.get("data", {})
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

    @classmethod
    @cache
    def load_fingerprints(cls) -> dict[str, Fingerprint]:
        with open(cls.get_fingerprint_path()) as f:
            fingerprints = json.loads(f.read())
        allowed = {item.name for item in fields(Fingerprint)}
        parsed = {}
        for key, payload in fingerprints.items():
            if not isinstance(payload, dict):
                continue
            filtered = {k: v for k, v in payload.items() if k in allowed}
            parsed[key] = Fingerprint(**filtered)
        return parsed
