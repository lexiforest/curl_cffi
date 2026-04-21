import os
import platform
import sys

import curl_cffi
from curl_cffi.fingerprints import FingerprintManager


def print_doctor() -> None:
    config_path = FingerprintManager.get_config_path()
    fingerprint_path = FingerprintManager.get_fingerprint_path()
    config_exists = os.path.exists(config_path)
    fingerprint_exists = os.path.exists(fingerprint_path)

    print("curl-cffi doctor")
    print("----------------")
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"machine: {platform.machine()}")
    print(f"curl_cffi: {curl_cffi.__version__}")
    print(f"libcurl: {curl_cffi.__curl_version__}")
    print(f"api_root: {FingerprintManager.get_api_root()}")
    print(f"config_path: {config_path}")
    print(f"config_present: {config_exists}")
    print(f"api_key_configured: {FingerprintManager.get_api_key() is not None}")
    print(f"fingerprint_path: {fingerprint_path}")
    print(f"fingerprint_present: {fingerprint_exists}")
    try:
        fingerprints = FingerprintManager.load_fingerprints()
    except FileNotFoundError:
        print("fingerprint_count: 0")
    except Exception as exc:
        print(f"fingerprint_count_error: {type(exc).__name__}")
    else:
        print(f"fingerprint_count: {len(fingerprints)}")
