import os
import json
from datetime import datetime
from enum import Enum
from typing import Optional, Literal
from dataclasses import dataclass, field

from .utils import HttpVersionLiteral

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


API_ROOT = "https://api.impersonate.pro/v1"
CONFIG_DIR = os.path.expanduser("~/.config/impersonate")


def cache_result(func):
    cache = {}

    def wrapper(*args, **kwargs):
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]

    return wrapper


def get_config_path():
    return os.path.join(CONFIG_DIR, "config.json")


def get_profile_path():
    return os.path.join(CONFIG_DIR, "profiles.json")


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
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)
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
    http_version: str = "v2"
    tls_version: int = 721
    ciphers: list[str] = field(default_factory=list)
    alpn: bool = False
    alps: bool = False
    cert_compression: list[str] = field(default_factory=list)
    signature_hashes: list[str] = field(default_factory=list)
    tls_supported_groups: list[str] = field(default_factory=list)
    tls_session_ticket: bool = False
    tls_extension_order: str = ""
    tls_delegated_credentials: list[str] = field(default_factory=list)
    tls_record_size_limit: Optional[int] = None
    tls_grease: bool = False
    tls_use_new_alps_codepoint: bool = False
    tls_signed_cert_timestamps: bool = False
    ech: Optional[str] = "grease"

    headers: dict[str, str] = field(default_factory=dict)

    http2_settings: str = ""
    http2_window_update: int = 0
    http2_pseudo_headers_order: str = "masp"
    http2_stream_weight: Optional[int] = None
    http2_stream_exclusive: Optional[int] = None
    http2_no_priority: bool = False

    http3_settings: str = ""


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


def update_profiles(api_root=API_ROOT):
    """Get the latest browser profiles for impersonating"""
    r = requests.get(api_root + "/profiles")
    data = r.json()

    profiles = {}

    for item in data["items"]:
        profiles[item["target"]] = item["profile"]

    with open(get_profile_path(), "w") as wf:
        wf.write(json.dumps(profiles))


def update_market_share(api_root=API_ROOT):
    """Get the latest market share of browsers"""


@cache_result
def load_profiles() -> dict[str, Profile]:
    with open(get_profile_path()) as f:
        profiles = json.loads(f.read())
    for key in profiles:
        profiles[key] = Profile(**profiles[key])

    return profiles


@cache_result
def load_market_share(): ...
