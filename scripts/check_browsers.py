"""Check that curl_cffi exposes every browser target of the pinned binary.

The compiled ``libcurl-impersonate`` supports the targets declared in the
upstream ``patches/curl.patch`` (``.target = "..."`` entries). This script
fetches that patch for the pinned version and verifies that every browser
target is exposed in both:

* ``BrowserTypeLiteral`` in ``curl_cffi/requests/impersonate.py``, and
* ``NATIVE_IMPERSONATE_TARGETS`` in ``curl_cffi/fingerprints.py``.

It exits non-zero (and prints what is missing) if a target was forgotten, so a
new browser version in the pinned binary can't silently go unexposed. Non-browser
http clients (``okhttp``, ``volley``, ``webview``) and hand-maintained aliases or
deprecated names are ignored.

Run manually or in CI::

    python scripts/check_browsers.py            # use the pinned version
    python scripts/check_browsers.py 2.0.0rc4   # override the version
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent
IMPERSONATE_FILE = ROOT / "curl_cffi" / "requests" / "impersonate.py"
FINGERPRINTS_FILE = ROOT / "curl_cffi" / "fingerprints.py"
BUILD_FILE = ROOT / "scripts" / "build.py"

PATCH_URL = (
    "https://raw.githubusercontent.com/lexiforest/curl-impersonate/"
    "v{version}/patches/curl.patch"
)

# Only these prefixes are browsers; everything else in the patch (okhttp4_android,
# volley, webview, ...) is an http client and intentionally not exposed.
BROWSER_PREFIXES = ("edge", "chrome", "safari", "firefox", "tor")


def read_pinned_version() -> str:
    match = re.search(
        r'^__version__\s*=\s*"([^"]+)"', BUILD_FILE.read_text(), re.MULTILINE
    )
    if not match:
        raise SystemExit(f"could not find __version__ in {BUILD_FILE}")
    return match.group(1)


def fetch_patch(version: str) -> str:
    url = PATCH_URL.format(version=version)
    print(f"fetching {url}")
    with urlopen(url, timeout=60) as response:  # noqa: S310 (trusted host)
        return response.read().decode()


def is_browser(target: str) -> bool:
    return target.startswith(BROWSER_PREFIXES)


def patch_targets(patch: str) -> set[str]:
    """Browser targets declared in the patch, de-duplicated."""
    return {t for t in re.findall(r'\.target = "([^"]+)"', patch) if is_browser(t)}


def _assigned_value(source: str, name: str) -> ast.expr:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in node.targets
        ):
            return node.value
    raise SystemExit(f"could not find assignment to {name}")


def literal_targets() -> set[str]:
    """String entries of ``BrowserTypeLiteral`` (comments are absent from the AST)."""
    value = _assigned_value(IMPERSONATE_FILE.read_text(), "BrowserTypeLiteral")
    # ``Literal[...]`` is a Subscript; its slice is a tuple of string constants.
    slice_node = value.slice if isinstance(value, ast.Subscript) else value
    elements = slice_node.elts if isinstance(slice_node, ast.Tuple) else [slice_node]
    return {
        el.value
        for el in elements
        if isinstance(el, ast.Constant) and isinstance(el.value, str)
    }


def fingerprint_targets() -> set[str]:
    """``target_name`` values in ``NATIVE_IMPERSONATE_TARGETS``."""
    value = _assigned_value(FINGERPRINTS_FILE.read_text(), "NATIVE_IMPERSONATE_TARGETS")
    if not isinstance(value, ast.List):
        raise SystemExit("NATIVE_IMPERSONATE_TARGETS is not a list literal")
    names: set[str] = set()
    for item in value.elts:
        if not isinstance(item, ast.Dict):
            continue
        for key, val in zip(item.keys, item.values, strict=True):
            if (
                isinstance(key, ast.Constant)
                and key.value == "target_name"
                and isinstance(val, ast.Constant)
                and isinstance(val.value, str)
            ):
                names.add(val.value)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "version",
        nargs="?",
        help="curl-impersonate version tag (default: pinned in scripts/build.py)",
    )
    args = parser.parse_args()

    version = args.version or read_pinned_version()
    expected = patch_targets(fetch_patch(version))
    if not expected:
        raise SystemExit("no browser targets parsed from patch; aborting")

    missing_literal = sorted(expected - literal_targets())
    missing_fp = sorted(expected - fingerprint_targets())

    if not missing_literal and not missing_fp:
        print(f"OK: all {len(expected)} browser targets of v{version} are exposed")
        return 0

    if missing_literal:
        print(f"missing from BrowserTypeLiteral: {missing_literal}")
    if missing_fp:
        print(f"missing from NATIVE_IMPERSONATE_TARGETS: {missing_fp}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
