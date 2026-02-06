import argparse
import os
import platform
import sys

import curl_cffi

from curl_cffi.fingerprints import FingerprintManager


def _add_fetch_parser(subparsers):
    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch a URL",
        description="Fetch a URL with optional browser impersonation.",
    )
    fetch_parser.add_argument(
        "-i",
        "--impersonate",
        default="chrome",
        help="Browser to impersonate",
    )
    fetch_parser.add_argument("urls", nargs="+", help="URLs to fetch")


def _add_update_parser(subparsers):
    subparsers.add_parser(
        "update",
        help="Update local fingerprints cache",
        description="Update fingerprints from the impersonate API.",
    )


def _add_list_parser(subparsers):
    subparsers.add_parser(
        "list",
        help="List local fingerprints",
        description="List fingerprints stored on disk.",
    )


def _add_config_parser(subparsers):
    config_parser = subparsers.add_parser(
        "config",
        help="Configure API access",
        description="Set the API key for impersonate.pro.",
    )
    config_parser.add_argument(
        "--api-key",
        required=True,
        help="API key for impersonate.pro",
    )


def _add_doctor_parser(subparsers):
    subparsers.add_parser(
        "doctor",
        help="Dump diagnostic information",
        description="Dump diagnostic information for debugging.",
    )


def _print_doctor():
    config_path = FingerprintManager.get_config_path()
    fingerprint_path = FingerprintManager.get_fingerprint_path()
    config_exists = os.path.exists(config_path)
    fingerprint_exists = os.path.exists(fingerprint_path)
    token_set = bool(os.environ.get("RVSD_SESSION_TOKEN"))

    print("curl-cffi doctor")
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"machine: {platform.machine()}")
    print(f"curl_cffi: {curl_cffi.__version__}")
    print(f"libcurl: {curl_cffi.__curl_version__}")
    print(f"api_root: {FingerprintManager.get_api_root()}")
    print(f"config_path: {config_path}")
    print(f"config_present: {config_exists}")
    print(f"api_key_configured: {FingerprintManager.is_pro()}")
    print(f"fingerprint_path: {fingerprint_path}")
    print(f"fingerprint_present: {fingerprint_exists}")
    print(f"rvsd_session_token_set: {token_set}")
    try:
        fingerprints = FingerprintManager.load_fingerprints()
    except FileNotFoundError:
        print("fingerprint_count: 0")
    except Exception as exc:
        print(f"fingerprint_count_error: {type(exc).__name__}")
    else:
        print(f"fingerprint_count: {len(fingerprints)}")


def main():
    parser = argparse.ArgumentParser(
        prog="curl-cffi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="A curl-like tool using curl-cffi with browser impersonation",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_fetch_parser(subparsers)
    _add_update_parser(subparsers)
    _add_list_parser(subparsers)
    _add_config_parser(subparsers)
    _add_doctor_parser(subparsers)

    args = parser.parse_args()

    if args.command == "update":
        FingerprintManager.update_fingerprints()
        return

    if args.command == "list":
        try:
            fingerprints = FingerprintManager.load_fingerprints()
        except FileNotFoundError:
            print("No local fingerprints found. Run `curl-cffi update` first.")
            return
        for fingerprint in fingerprints:
            print(fingerprint)
        return

    if args.command == "config":
        FingerprintManager.enable_pro(args.api_key)
        print("API key saved.")
        return

    if args.command == "doctor":
        _print_doctor()
        return

    if args.command == "fetch":
        for url in args.urls:
            try:
                response = curl_cffi.requests.get(url, impersonate=args.impersonate)
                print(response.text)
            except Exception as e:
                print(f"Error fetching {url}: {e}", file=sys.stderr)
                sys.exit(1)


if __name__ == "__main__":
    main()
