#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pathlib
import re
import urllib.error
import urllib.request


ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent
FORMULA_PATH = ROOT_DIR / "Formula" / "curl-cffi.rb"
PYPROJECT_PATH = ROOT_DIR / "pyproject.toml"
PACKAGE_NAME = "curl-cffi"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update Formula/curl-cffi.rb with the PyPI sdist URL/SHA256 and the "
            "macOS wheel URL/SHA256 values for arm64 and x86_64."
        )
    )
    parser.add_argument(
        "version",
        nargs="?",
        help="Release version to use. Defaults to the version in pyproject.toml.",
    )
    return parser.parse_args()


def project_version(pyproject_path: pathlib.Path) -> str:
    text = pyproject_path.read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
    if match is None:
        raise SystemExit("Could not find [project].version in pyproject.toml")
    return match.group(1)


def load_pypi_payload(version: str) -> dict:
    url = f"https://pypi.org/pypi/{PACKAGE_NAME}/{version}/json"
    try:
        with urllib.request.urlopen(url) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"PyPI returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to fetch {url}: {exc.reason}") from exc


def select_file(
    urls: list[dict],
    *,
    packagetype: str,
    python_version: str | None = None,
    suffix: str | None = None,
) -> dict:
    matches = []
    for item in urls:
        if item.get("packagetype") != packagetype:
            continue
        if python_version is not None and item.get("python_version") != python_version:
            continue
        filename = item.get("filename", "")
        if suffix is not None and not filename.endswith(suffix):
            continue
        matches.append(item)

    if len(matches) != 1:
        detail = (
            f"packagetype={packagetype!r}, python_version={python_version!r}, "
            f"suffix={suffix!r}"
        )
        raise SystemExit(
            f"Expected exactly one matching file for {detail}, found {len(matches)}"
        )

    return matches[0]


def replace_once(text: str, pattern: str, replacement: str, *, count: int = 1) -> str:
    new_text, replaced = re.subn(pattern, replacement, text, count=count, flags=re.MULTILINE)
    if replaced != count:
        raise SystemExit(f"Expected to replace {count} match(es) for pattern: {pattern!r}")
    return new_text


def replace_indented_field(text: str, field: str, value: str) -> str:
    pattern = rf'^(\s+){field} ".*"$'

    def repl(match: re.Match[str]) -> str:
        return f'{match.group(1)}{field} "{value}"'

    new_text, replaced = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if replaced != 1:
        raise SystemExit(f'Expected exactly one "{field}" entry in resource block')
    return new_text


def update_formula(formula_path: pathlib.Path, version: str, payload: dict) -> tuple[str, str, str]:
    urls = payload.get("urls", [])
    if not urls:
        raise SystemExit("No files were returned by the PyPI API")

    sdist = select_file(urls, packagetype="sdist", suffix=".tar.gz")
    arm64 = select_file(
        urls,
        packagetype="bdist_wheel",
        python_version="cp310",
        suffix="macosx_11_0_arm64.whl",
    )
    x86_64 = select_file(
        urls,
        packagetype="bdist_wheel",
        python_version="cp310",
        suffix="macosx_10_9_x86_64.whl",
    )

    text = formula_path.read_text(encoding="utf-8")
    text = replace_once(text, r'^  url ".*"$', f'  url "{sdist["url"]}"')
    text = replace_once(text, r'^  version ".*"$', f'  version "{version}"')
    text = replace_once(text, r'^  sha256 ".*"$', f'  sha256 "{sdist["digests"]["sha256"]}"')

    resource_pattern = re.compile(
        r'(^\s+resource "curl-cffi" do\n)(.*?)(^\s+end$)',
        re.MULTILINE | re.DOTALL,
    )
    matches = list(resource_pattern.finditer(text))
    if len(matches) != 2:
        raise SystemExit(f'Expected 2 "curl-cffi" resource blocks, found {len(matches)}')

    updated_parts = []
    last_end = 0
    for match, artifact in zip(matches, (arm64, x86_64), strict=True):
        body = match.group(2)
        body = replace_indented_field(body, "url", artifact["url"])
        body = replace_indented_field(body, "sha256", artifact["digests"]["sha256"])
        updated_parts.append(text[last_end:match.start()])
        updated_parts.append(f"{match.group(1)}{body}{match.group(3)}")
        last_end = match.end()
    updated_parts.append(text[last_end:])

    formula_path.write_text("".join(updated_parts), encoding="utf-8")
    return sdist["filename"], arm64["filename"], x86_64["filename"]


def main():
    args = parse_args()
    version = args.version or project_version(PYPROJECT_PATH)
    payload = load_pypi_payload(version)
    sdist_name, arm64_name, x86_64_name = update_formula(FORMULA_PATH, version, payload)

    print(f"Updated {FORMULA_PATH}")
    print(f"  version: {version}")
    print(f"  sdist:   {sdist_name}")
    print(f"  arm64:   {arm64_name}")
    print(f"  x86_64:  {x86_64_name}")


if __name__ == "__main__":
    main()
