from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field

from curl_cffi.requests import Session

from .parse import SUPPORTED_METHODS, process_url
from .request import _execute_request


# ---------------------------------------------------------------------------
# .http file support
# see: https://github.com/JetBrains/http-request-in-editor-spec/blob/master/spec.md
# ---------------------------------------------------------------------------


@dataclass
class HttpFileRequest:
    """A single request parsed from an .http file."""

    method: str = "GET"
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""


def parse_http_file(text: str) -> list[HttpFileRequest]:
    """Parse an .http file into a list of requests.

    Supports the HTTP Request in Editor spec:
    - Requests separated by ###
    """
    blocks = []
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.strip().startswith("###"):
            if current_lines:
                blocks.append(current_lines)
                current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        blocks.append(current_lines)

    requests = []
    for block_lines in blocks:
        req = _parse_http_block(block_lines)
        if req is not None:
            requests.append(req)
    return requests


def _parse_http_block(lines: list[str]) -> HttpFileRequest | None:
    """Parse a single request block from an .http file.

    Each block contains:
    - Request line: [METHOD] URL [HTTP/version]
    - Headers: Name: Value
    - Body after blank line
    - Comments with # or //
    - File references: < filepath
    """
    # States: "request" -> "headers" -> "body"
    state = "request"
    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        # skip any comments
        if stripped.startswith("#") or stripped.startswith("//"):
            continue

        match state:
            case "request":
                if not stripped:
                    continue
                parts = stripped.split()
                if (
                    parts[0].upper() in SUPPORTED_METHODS
                    or parts[0].upper() == "CONNECT"
                ):
                    method = parts[0].upper()
                    url = parts[1] if len(parts) > 1 else ""
                else:
                    url = parts[0]  # GET implied
                state = "headers"

            case "headers":
                if not stripped:
                    state = "body"  # blank line means body
                elif ":" in stripped:
                    name, _, value = stripped.partition(":")
                    headers[name.strip()] = value.strip()
                else:
                    state = "body"
                    body_lines.append(line)

            case "body":
                if stripped.startswith("> ") or stripped.startswith("<> "):
                    # TODO: implement body checking
                    break
                if stripped.startswith("< "):
                    _, filepath = stripped.split()
                    filepath = filepath.strip()
                    try:
                        with open(filepath) as f:
                            body_lines.append(f.read())
                    except FileNotFoundError:
                        print(
                            f"Error: referenced file not found: {filepath}",
                            file=sys.stderr,
                        )
                else:
                    body_lines.append(line)

    if not url:
        return None

    return HttpFileRequest(
        method=method,
        url=url,
        headers=headers,
        body="\n".join(body_lines).strip(),
    )


def _run_http_file(
    args: argparse.Namespace, text: str, session: Session | None = None
) -> int:
    """Execute requests parsed from .http file content."""

    requests = parse_http_file(text)
    if not requests:
        print("Error: no requests found in file.", file=sys.stderr)
        sys.exit(1)

    failed = 0
    for i, req in enumerate(requests, 1):
        print(f"--- [{i}] {req.method} {req.url}", file=sys.stderr)

        url = process_url(req.url)

        rc = _execute_request(
            args,
            req.method,
            url,
            headers=req.headers,
            data=req.body or None,
            session=session,
        )
        if rc != 0:
            failed += 1

    return failed


# ---------------------------------------------------------------------------
# HAR file support
# ---------------------------------------------------------------------------

_SKIP_HAR_HEADERS = frozenset(
    {
        "content-length",
        "transfer-encoding",
        ":method",
        ":path",
        ":scheme",
        ":authority",
    }
)


def _run_har_file(
    args: argparse.Namespace, text: str, session: Session | None = None
) -> int:
    """Execute requests parsed from HAR file content."""
    try:
        har = json.loads(text)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid HAR JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    entries = har.get("log", {}).get("entries", [])
    if not entries:
        print("Error: no entries found in HAR file.", file=sys.stderr)
        sys.exit(1)

    failed = 0
    for i, entry in enumerate(entries, 1):
        req = entry.get("request", {})
        method = req.get("method", "GET").upper()
        url = req.get("url", "")

        if not url:
            print(f"--- [{i}] skipping entry with no URL", file=sys.stderr)
            continue

        print(f"--- [{i}] {method} {url}", file=sys.stderr)

        headers = {}
        for h in req.get("headers", []):
            name = h.get("name", "")
            if name.lower() not in _SKIP_HAR_HEADERS:
                headers[name] = h.get("value", "")
        headers = headers or None

        post_data = req.get("postData")
        data = post_data.get("text", "") if post_data else None

        rc = _execute_request(
            args,
            method,
            url,
            headers=headers,
            data=data,
            session=session,
        )
        if rc != 0:
            failed += 1

    return failed


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def handle_run(args: argparse.Namespace) -> None:
    """Execute batch requests."""
    filepath = args.file
    try:
        with open(filepath) as f:
            text = f.read()
    except FileNotFoundError:
        print(f"Error: file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    use_session = getattr(args, "session", True)
    session = Session(impersonate=args.impersonate) if use_session else None

    try:
        if filepath.endswith(".har"):
            failed = _run_har_file(args, text, session=session)
        elif filepath.endswith(".http"):
            failed = _run_http_file(args, text, session=session)
        else:
            print(f"Error: unsupported file format: {filepath}", file=sys.stderr)
            sys.exit(1)
    finally:
        if session:
            session.close()

    if failed > 0:
        print(f"\n{failed} request(s) failed.", file=sys.stderr)
        sys.exit(1)
