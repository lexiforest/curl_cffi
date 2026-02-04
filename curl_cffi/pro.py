import os
import json
from datetime import datetime
from typing import Optional, Literal
from dataclasses import dataclass, field, fields

from . import requests


__all__ = [
    "Profile",
    "is_pro",
    "enable_pro",
    "update_profiles",
    "load_profiles",
    "update_market_share",
    "load_market_share",
]


"""
Pro config example
{
    "api_key": "imp_xxxxxx",
    "updated_at": "2025-08-26 18:01:01" | null
}
"""


DEFAULT_API_ROOT = "https://api.impersonate.pro/v1"
DEFAULT_CONFIG_DIR = os.path.expanduser("~/.config/impersonate")
# Backward-compatible constant for external imports.
CONFIG_DIR = DEFAULT_CONFIG_DIR


def get_config_dir() -> str:
    return os.environ.get("IMPERSONATE_CONFIG_DIR", DEFAULT_CONFIG_DIR)


def cache_result(func):
    cache = {}

    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]

    return wrapper


def get_config_path():
    return os.path.join(get_config_dir(), "config.json")


def get_profile_path():
    return os.path.join(get_config_dir(), "profiles.json")


def get_api_root() -> str:
    return os.environ.get("IMPERSONATE_API_ROOT", DEFAULT_API_ROOT)


@cache_result
def is_pro():
    config_file = get_config_path()
    if not os.path.exists(config_file):
        return False
    with open(config_file) as f:
        try:
            config = json.load(f)
            return config.get("api_key") not in [None, ""]
        except json.JSONDecodeError:
            return False


def enable_pro(api_key: str):
    """Enable the pro version"""
    config_dir = get_config_dir()
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    config_file = get_config_path()
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


@dataclass
class Profile:
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
    tls_record_size_limit: Optional[int] = None
    tls_grease: bool = False
    tls_use_new_alps_codepoint: bool = False
    tls_signed_cert_timestamps: bool = False
    tls_ech: Optional[str] = None

    headers: dict[str, str] = field(default_factory=dict)

    http2_settings: str = ""
    http2_window_update: int = 0
    http2_pseudo_headers_order: str = ""
    http2_stream_weight: Optional[int] = None
    http2_stream_exclusive: Optional[int] = None
    http2_no_priority: bool = False
    http2_priority_exclusive: Optional[int] = None

    http3_settings: str = ""
    quic_transport_parameters: str = ""

    header_lang: str = ""


# fmt: off
ClientLiteral = Literal[
    # browsers,
    "chrome", "firefox", "edge", "brave", "opera", "brave", "operamini",
    "qihoo", "qq", "quark", "samsung", "sogou", "sogou_ie",
    # http client,
    "volley", "okhttp", "webview",
    # app with web view
    "baidu", "wechat", "bing", "duckduckgo", "google", "yandex",
]
# fmt: on
PlatformLiteral = ["macos", "windows", "linux", "ios", "android"]


@dataclass
class ProfileSpec:
    platform: Optional[str] = None
    client: Optional[ClientLiteral] = None
    strategy: Optional[Literal["uniform", "market_share"]] = "market_share"


def update_profiles(
    api_root: Optional[str] = None,
    session_token: Optional[str] = None,
) -> None:
    """Get the latest fingerprints for impersonating."""
    api_root = api_root or get_api_root()
    token = session_token or os.environ.get("RVSD_SESSION_TOKEN")
    cookies = {"rvsd.session_token": token} if token else None
    url = f"{api_root.rstrip('/')}/fingerprints"
    r = requests.get(url, cookies=cookies)
    data = r.json()
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("Fingerprints API returned unexpected payload.")

    profiles = {}
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
            profiles[name] = raw

    config_dir = get_config_dir()
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)
    with open(get_profile_path(), "w") as wf:
        json.dump(profiles, wf, indent=2)


def update_market_share(api_root: Optional[str] = None):
    """Get the latest market share of browsers"""
    api_root = api_root or get_api_root()


@cache_result
def load_profiles() -> dict[str, Profile]:
    with open(get_profile_path()) as f:
        profiles = json.loads(f.read())
    allowed = {item.name for item in fields(Profile)}
    parsed = {}
    for key, payload in profiles.items():
        if not isinstance(payload, dict):
            continue
        filtered = {k: v for k, v in payload.items() if k in allowed}
        parsed[key] = Profile(**filtered)
    return parsed


@cache_result
def load_market_share(): ...
