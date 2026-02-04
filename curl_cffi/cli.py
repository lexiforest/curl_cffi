import argparse
import os
import platform
import sys

import curl_cffi

from curl_cffi.pro import (
    enable_pro,
    get_api_root,
    get_config_path,
    get_profile_path,
    is_pro,
    load_profiles,
    update_profiles,
)


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
    config_path = get_config_path()
    profile_path = get_profile_path()
    config_exists = os.path.exists(config_path)
    profile_exists = os.path.exists(profile_path)
    token_set = bool(os.environ.get("RVSD_SESSION_TOKEN"))

    print("curl-cffi doctor")
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"machine: {platform.machine()}")
    print(f"curl_cffi: {curl_cffi.__version__}")
    print(f"libcurl: {curl_cffi.__curl_version__}")
    print(f"api_root: {get_api_root()}")
    print(f"config_path: {config_path}")
    print(f"config_present: {config_exists}")
    print(f"api_key_configured: {is_pro()}")
    print(f"profile_path: {profile_path}")
    print(f"profile_present: {profile_exists}")
    print(f"rvsd_session_token_set: {token_set}")
    try:
        profiles = load_profiles()
    except FileNotFoundError:
        print("profile_count: 0")
    except Exception as exc:
        print(f"profile_count_error: {type(exc).__name__}")
    else:
        print(f"profile_count: {len(profiles)}")


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
        update_profiles()
        return

    if args.command == "list":
        try:
            profiles = load_profiles()
        except FileNotFoundError:
            print("No local fingerprints found. Run `curl-cffi update` first.")
            return
        for profile in profiles:
            print(profile)
        return

    if args.command == "config":
        enable_pro(args.api_key)
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
