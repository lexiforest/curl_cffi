import argparse
import json
import os
import platform
import sys

import curl_cffi

from curl_cffi.fingerprints import FingerprintManager


def _validate_api_key(value: str) -> str:
    if not value.startswith("imp_"):
        raise argparse.ArgumentTypeError("API key must start with 'imp_'.")
    return value


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
    list_parser = subparsers.add_parser(
        "list",
        help="List local and native fingerprints",
        description="List local and native fingerprints.",
    )
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="Output fingerprints as JSON.",
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
        type=_validate_api_key,
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
    print(f"api_key_configured: {FingerprintManager.is_pro()}")
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


def _format_cell(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _print_table(headers: list[str], rows: list[list[str]]):
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))

    def render_row(row_values: list[str]) -> str:
        return " | ".join(
            value.ljust(widths[idx]) for idx, value in enumerate(row_values)
        )

    print(render_row(headers))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(render_row(row))


def _print_fingerprints_table(fingerprint_rows: list[dict[str, object]]):
    headers = [
        "type",
        "name",
        "browser",
        "version",
        "os",
        "os_version",
        "h3_fingerprints",
    ]
    rows: list[list[str]] = []
    for item in fingerprint_rows:
        row = [_format_cell(item[header]) for header in headers]
        rows.append(row)
    _print_table(headers, rows)


def _print_fingerprints_json(rows: list[dict[str, object]]):
    print(json.dumps(rows, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(
        prog="curl-cffi",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="curl-cffi commandline interface",
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
        rows = FingerprintManager.list_fingerprints()
        if args.json:
            _print_fingerprints_json(rows)
            return
        _print_fingerprints_table(rows)
        return

    if args.command == "config":
        FingerprintManager.enable_pro(args.api_key)
        print("API key saved to " + FingerprintManager.get_config_path())
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
