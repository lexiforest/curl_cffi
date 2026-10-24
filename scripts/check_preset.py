#!/usr/bin/env python3

from __future__ import annotations

import argparse
import ast
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ROOT_DIR = Path(__file__).resolve().parent.parent
IMPERSONATE_PATH = ROOT_DIR / "curl_cffi" / "requests" / "impersonate.py"
FINGERPRINTS_PATH = ROOT_DIR / "curl_cffi" / "fingerprints.py"
BUILD_PATH = ROOT_DIR / "scripts" / "build.py"
MAKEFILE_PATH = ROOT_DIR / "Makefile"

PATCH_URL = (
    "https://raw.githubusercontent.com/lexiforest/curl-impersonate/"
    "v{version}/patches/curl.patch"
)
FETCH_ATTEMPTS = 3
# Targets of the binary that are http clients, not browsers, so not exposed. Any
# other target must be exposed, so that a new browser family isn't missed.
NON_BROWSER_TARGETS = {"okhttp4_android"}

DEFAULT_ALIAS_MAP = {
    "chrome": "DEFAULT_CHROME",
    "edge": "DEFAULT_EDGE",
    "safari": "DEFAULT_SAFARI",
    "safari_ios": "DEFAULT_SAFARI_IOS",
    "safari_beta": "DEFAULT_SAFARI_BETA",
    "safari_ios_beta": "DEFAULT_SAFARI_IOS_BETA",
    "chrome_android": "DEFAULT_CHROME_ANDROID",
    "firefox": "DEFAULT_FIREFOX",
    "tor": "DEFAULT_TOR",
}


def find_assignment_value(module: ast.Module, name: str) -> object:
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
    raise SystemExit(f"Could not find assignment for {name!r}")


def extract_literal_items(text: str, name: str, stop_comment: str) -> list[str]:
    pattern = re.compile(rf"^{name}\s*=\s*Literal\[$", re.MULTILINE)
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"Could not find Literal block for {name!r}")

    items: list[str] = []
    for line in text[match.end() :].splitlines():
        stripped = line.strip()
        if stripped == "]":
            break
        if stripped == stop_comment:
            break
        if stripped.startswith("#") or not stripped:
            continue
        value = ast.literal_eval(stripped.rstrip(","))
        if not isinstance(value, str):
            raise SystemExit(f"Unexpected Literal value in {name!r}: {stripped}")
        items.append(value)
    return items


def extract_enum_values(text: str, class_name: str, stop_comment: str) -> list[str]:
    pattern = re.compile(
        rf"^class {class_name}\(str, Enum\):.*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    if match is None:
        raise SystemExit(f"Could not find enum class {class_name!r}")

    values: list[str] = []
    for line in text[match.end() :].splitlines():
        stripped = line.strip()
        if stripped == stop_comment:
            break
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith("    "):
            break
        member_match = re.match(r'^\s+\w+\s*=\s*"([^"]+)"$', line)
        if member_match:
            values.append(member_match.group(1))
    return values


def format_values(values: list[str]) -> str:
    return ", ".join(values)


def pinned_version(errors: list[str]) -> str:
    """The curl-impersonate version, pinned in both build.py and the Makefile."""
    build_match = re.search(
        r'^__version__\s*=\s*"([^"]+)"$',
        BUILD_PATH.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    make_match = re.search(
        r"^VERSION\s*:=\s*(\S+)$",
        MAKEFILE_PATH.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if build_match is None:
        raise SystemExit(f"Could not find __version__ in {BUILD_PATH}")
    if make_match is None:
        raise SystemExit(f"Could not find VERSION in {MAKEFILE_PATH}")
    version = build_match.group(1)
    if make_match.group(1) != version:
        errors.append(
            f"Makefile pins curl-impersonate {make_match.group(1)}, "
            f"but scripts/build.py pins {version}"
        )
    return version


def fetch_patch(version: str) -> str:
    url = PATCH_URL.format(version=version)
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            with urlopen(url, timeout=60) as response:  # noqa: S310 (fixed host)
                return response.read().decode("utf-8")
        except URLError as e:
            # Only retry errors that may be transient, a missing tag stays missing.
            permanent = isinstance(e, HTTPError) and e.code < 500
            if permanent or attempt == FETCH_ATTEMPTS:
                raise SystemExit(f"Could not fetch {url}: {e}") from e
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def binary_targets(version: str) -> set[str]:
    """Browser targets compiled into the pinned curl-impersonate."""
    targets = set(re.findall(r'\.target = "([^"]+)"', fetch_patch(version)))
    targets -= NON_BROWSER_TARGETS
    if not targets:
        raise SystemExit(f"No targets found in the curl.patch of v{version}")
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check that the impersonate presets are consistent with each "
        "other and with the targets of the pinned curl-impersonate."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the comparison with the pinned curl-impersonate",
    )
    args = parser.parse_args()

    impersonate_text = IMPERSONATE_PATH.read_text(encoding="utf-8")
    fingerprints_text = FINGERPRINTS_PATH.read_text(encoding="utf-8")
    impersonate_ast = ast.parse(impersonate_text, filename=str(IMPERSONATE_PATH))
    fingerprints_ast = ast.parse(fingerprints_text, filename=str(FINGERPRINTS_PATH))

    literal_targets = set(
        extract_literal_items(
            impersonate_text, "BrowserTypeLiteral", stop_comment="# alias"
        )
    )
    enum_targets = set(
        extract_enum_values(
            impersonate_text, "BrowserType", stop_comment="# deprecated aliases"
        )
    )
    defaults = find_assignment_value(impersonate_ast, "REAL_TARGET_MAP")
    default_constants = {
        name: find_assignment_value(impersonate_ast, name)
        for name in DEFAULT_ALIAS_MAP.values()
    }
    native_targets = find_assignment_value(
        fingerprints_ast, "NATIVE_IMPERSONATE_TARGETS"
    )

    if not isinstance(defaults, dict):
        raise SystemExit("REAL_TARGET_MAP must be a dict literal")
    if not isinstance(native_targets, list):
        raise SystemExit("NATIVE_IMPERSONATE_TARGETS must be a list literal")

    real_target_map = {str(key): str(value) for key, value in defaults.items()}
    native_target_names = {
        item["target_name"]
        for item in native_targets
        if isinstance(item, dict) and isinstance(item.get("target_name"), str)
    }

    errors: list[str] = []

    if literal_targets != enum_targets:
        missing_in_enum = sorted(literal_targets - enum_targets)
        missing_in_literal = sorted(enum_targets - literal_targets)
        if missing_in_enum:
            errors.append(
                "BrowserType is missing concrete presets from BrowserTypeLiteral: "
                + format_values(missing_in_enum)
            )
        if missing_in_literal:
            errors.append(
                "BrowserTypeLiteral is missing concrete presets from BrowserType: "
                + format_values(missing_in_literal)
            )

    missing_in_fingerprints = sorted(literal_targets - native_target_names)
    extra_in_fingerprints = sorted(native_target_names - literal_targets)
    if missing_in_fingerprints:
        errors.append(
            "fingerprints.py is missing concrete presets from impersonate.py: "
            + format_values(missing_in_fingerprints)
        )
    if extra_in_fingerprints:
        errors.append(
            "fingerprints.py has target_name entries not declared in impersonate.py: "
            + format_values(extra_in_fingerprints)
        )

    for alias, default_name in DEFAULT_ALIAS_MAP.items():
        default_value = default_constants[default_name]
        if not isinstance(default_value, str):
            raise SystemExit(f"{default_name} must be a string literal")
        if default_value not in literal_targets:
            errors.append(f"{default_name} points to unknown preset {default_value!r}")
        mapped_value = real_target_map.get(alias)
        if mapped_value != default_value:
            errors.append(
                f"REAL_TARGET_MAP[{alias!r}]={mapped_value!r} does not match "
                f"{default_name}={default_value!r}"
            )
        if default_value not in native_target_names:
            errors.append(
                f"{default_name}={default_value!r} is missing from "
                "NATIVE_IMPERSONATE_TARGETS"
            )

    version = None
    if not args.offline:
        version = pinned_version(errors)
        compiled_targets = binary_targets(version)
        unexposed = sorted(compiled_targets - literal_targets)
        unsupported = sorted(literal_targets - compiled_targets)
        if unexposed:
            errors.append(
                f"impersonate.py is missing targets of curl-impersonate v{version}: "
                + format_values(unexposed)
            )
        if unsupported:
            errors.append(
                f"impersonate.py has presets that curl-impersonate v{version} "
                "doesn't support: " + format_values(unsupported)
            )

    if errors:
        print("Preset consistency check failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        "Preset consistency check passed for "
        f"{IMPERSONATE_PATH.relative_to(ROOT_DIR)} and "
        f"{FINGERPRINTS_PATH.relative_to(ROOT_DIR)}"
        + (f", against curl-impersonate v{version}" if version else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
