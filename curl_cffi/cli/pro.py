"""Pro subcommands: update, list, config (fingerprint management)."""

from __future__ import annotations

import argparse
import json
import sys

from curl_cffi.fingerprints import FingerprintManager, FingerprintUpdateError


def _validate_api_key(value: str) -> str:
    if not value.startswith("imp_"):
        raise argparse.ArgumentTypeError("API key must start with 'imp_'.")
    return value


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


def add_pro_parsers(subparsers) -> None:
    """Register update, list, and config subcommands."""
    # update
    subparsers.add_parser(
        "update",
        help="Update local fingerprints cache",
        description="Update fingerprints from the impersonate API.",
    )

    # list
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

    # config
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


def handle_pro_command(args) -> bool:
    """Handle pro subcommands. Returns True if handled, False otherwise."""
    if args.command == "update":
        try:
            updated = FingerprintManager.update_fingerprints()
        except FingerprintUpdateError as exc:
            print(str(exc), file=sys.stderr)
        else:
            suffix = "" if updated == 1 else "s"
            print(f"Total {updated} fingerprint{suffix} in cache.")
        return True

    if args.command == "list":
        rows = FingerprintManager.list_fingerprints()
        if args.json:
            _print_fingerprints_json(rows)
        else:
            _print_fingerprints_table(rows)
        return True

    if args.command == "config":
        FingerprintManager.set_api_key(args.api_key)
        print("API key saved to " + FingerprintManager.get_config_path())
        return True

    return False
