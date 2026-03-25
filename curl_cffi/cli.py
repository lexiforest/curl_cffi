import argparse
import json
import platform
import sys
from dataclasses import dataclass, field

import curl_cffi
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

SUPPORTED_METHODS = {
    "GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "TRACE", "PATCH", "QUERY",
}


# ---------------------------------------------------------------------------
# URL processing
# ---------------------------------------------------------------------------

def process_url(url: str) -> str:
    """Normalise a URL: localhost shortcut, default scheme."""
    if url.startswith(":"):
        return f"http://localhost{url}"
    if "://" not in url:
        return f"https://{url}"
    return url


# ---------------------------------------------------------------------------
# Request object parsing
# ---------------------------------------------------------------------------

@dataclass
class ParsedItems:
    headers: dict[str, str] = field(default_factory=dict)
    headers_to_remove: list[str] = field(default_factory=list)
    query_params: list[tuple[str, str]] = field(default_factory=list)
    data_fields: list[tuple[str, str]] = field(default_factory=list)
    json_fields: list[tuple[str, object]] = field(default_factory=list)
    files: list[tuple[str, str]] = field(default_factory=list)


def parse_request_items(items: list[str]) -> ParsedItems:
    """Parse request items into structured data."""
    result = ParsedItems()
    for item in items:
        if ":=" in item:
            key, _, value = item.partition(":=")
            try:
                result.json_fields.append((key, json.loads(value)))
            except json.JSONDecodeError as exc:
                print(f"Error: invalid JSON in '{item}': {exc}", file=sys.stderr)
                sys.exit(1)
        elif "==" in item:
            key, _, value = item.partition("==")
            result.query_params.append((key, value))
        elif "=" in item:
            key, _, value = item.partition("=")
            result.data_fields.append((key, value))
        elif item.startswith("@"):
            filepath = item[1:]
            result.files.append(("file", filepath))
        elif ":" in item:
            key, _, value = item.partition(":")
            if value:
                result.headers[key] = value
            else:
                result.headers_to_remove.append(key)
        else:
            print(f"Error: unknown request item '{item}'", file=sys.stderr)
            sys.exit(1)
    return result


# ---------------------------------------------------------------------------
# Positional extraction
# ---------------------------------------------------------------------------

def extract_positionals(
    remaining: list[str],
) -> tuple[str | None, str, list[str]]:
    """Extract (method, url, request_items) from unrecognised positional args."""
    if not remaining:
        print("Error: URL is required.", file=sys.stderr)
        sys.exit(1)

    method = None
    idx = 0

    if remaining[0].upper() in SUPPORTED_METHODS:
        method = remaining[0].upper()
        idx = 1

    if idx >= len(remaining):
        print("Error: URL is required.", file=sys.stderr)
        sys.exit(1)

    url = remaining[idx]
    request_items = remaining[idx + 1:]
    return method, url, request_items


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _http_ver_label(response) -> str:
    from curl_cffi.const import CurlHttpVersion

    v = getattr(response, "http_version", 0)
    mapping = {
        CurlHttpVersion.V1_0: "1.0",
        CurlHttpVersion.V1_1: "1.1",
        CurlHttpVersion.V2_0: "2",
        CurlHttpVersion.V2TLS: "2",
        CurlHttpVersion.V2_PRIOR_KNOWLEDGE: "2",
        CurlHttpVersion.V3: "3",
        CurlHttpVersion.V3ONLY: "3",
    }
    return mapping.get(v, "1.1")


def determine_print_spec(args) -> str:
    if args.print_spec:
        return args.print_spec
    if args.verbose:
        return "HhBb"
    if args.headers_only:
        return "h"
    if args.body_only:
        return "b"
    if args.download:
        return "h"
    if sys.stdout.isatty():
        return "hb"
    return "b"


def _print_headers(console, lines):
    """Print HTTP headers with rich colors."""
    for line in lines:
        if ": " in line:
            key, _, value = line.partition(": ")
            text = Text()
            text.append(key, style="bold cyan")
            text.append(": ", style="dim")
            text.append(value)
            console.print(text)
        else:
            # Status line or request line
            console.print(Text(line, style="bold green"))


def _print_body(console, response):
    """Print response body, syntax-highlighted if JSON."""
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            formatted = json.dumps(response.json(), indent=2, ensure_ascii=False)
            console.print(Syntax(formatted, "json", theme="monokai", word_wrap=True))
            return
        except (json.JSONDecodeError, ValueError):
            pass
    if "html" in content_type:
        console.print(Syntax(response.text, "html", theme="monokai", word_wrap=True))
    elif "xml" in content_type:
        console.print(Syntax(response.text, "xml", theme="monokai", word_wrap=True))
    else:
        console.print(response.text, highlight=False)


def print_output(response, method, url, request_headers, request_body, print_spec):
    use_color = sys.stdout.isatty()
    console = Console(force_terminal=use_color, no_color=not use_color)

    if "H" in print_spec:
        lines = [f"{method} {url}"]
        for k, v in (request_headers or {}).items():
            lines.append(f"{k}: {v}")
        if use_color:
            _print_headers(console, lines)
        else:
            for line in lines:
                print(line)
        print()

    if "B" in print_spec and request_body:
        if use_color:
            console.print(Syntax(request_body, "json", theme="monokai", word_wrap=True))
        else:
            print(request_body)
        print()

    if "h" in print_spec:
        ver = _http_ver_label(response)
        status_line = f"HTTP/{ver} {response.status_code} {response.reason}"
        header_lines = [f"{k}: {v}" for k, v in response.headers.items()]
        if use_color:
            # Color the status line based on status code
            if response.status_code < 300:
                style = "bold green"
            elif response.status_code < 400:
                style = "bold yellow"
            else:
                style = "bold red"
            console.print(Text(status_line, style=style))
            _print_headers(console, header_lines)
        else:
            print(status_line)
            for line in header_lines:
                print(line)
        print()

    if "b" in print_spec:
        if use_color:
            _print_body(console, response)
        else:
            content_type = response.headers.get("content-type", "")
            if "json" in content_type:
                try:
                    formatted = json.dumps(response.json(), indent=2, ensure_ascii=False)
                    print(formatted)
                except (json.JSONDecodeError, ValueError):
                    print(response.text)
            else:
                print(response.text)


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

def handle_download(response, url, output_path=None):
    if output_path is None:
        cd = response.headers.get("content-disposition", "")
        if "filename=" in cd:
            output_path = cd.split("filename=")[1].strip('"').strip("'")
        else:
            output_path = url.rstrip("/").split("/")[-1] or "download"

    with open(output_path, "wb") as f:
        f.write(response.content)
    print(f"Downloaded to {output_path}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Doctor
# ---------------------------------------------------------------------------

def print_doctor():
    print("curl-cffi doctor")
    print("----------------")
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"machine: {platform.machine()}")
    print(f"curl_cffi: {curl_cffi.__version__}")
    print(f"libcurl: {curl_cffi.__curl_version__}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="curl-cffi",
        description="HTTP request CLI with browser impersonation.\n\n"
        "Usage:\n"
        "  curl-cffi [FLAGS] [METHOD] URL [REQUEST_ITEMS...]\n"
        "  curl-cffi doctor\n\n"
        "Request items:\n"
        "  Header:Value   HTTP header\n"
        "  param==value   Query parameter\n"
        "  field=value    Data field\n"
        "  field:=json    Raw JSON field\n"
        "  @file          File upload\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Content type
    content_group = parser.add_mutually_exclusive_group()
    content_group.add_argument(
        "--json", "-j", action="store_true", dest="json_mode",
        help="(default) Serialize data items as a JSON object",
    )
    content_group.add_argument(
        "--form", "-f", action="store_true",
        help="Serialize data items as form fields",
    )
    content_group.add_argument(
        "--multipart", action="store_true",
        help="Force multipart form data",
    )

    # Output control
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--headers", action="store_true", dest="headers_only",
        help="Print response headers only",
    )
    output_group.add_argument(
        "--body", action="store_true", dest="body_only",
        help="Print response body only",
    )
    output_group.add_argument(
        "--verbose", "-v", action="store_true",
        help="Print request and response headers and body",
    )
    output_group.add_argument(
        "--print", "-p", dest="print_spec", default=None,
        help="Fine-grained output control: H(request headers) B(request body) h(response headers) b(response body)",
    )

    # Download
    parser.add_argument(
        "--download", "-d", action="store_true",
        help="Download response body to file",
    )
    parser.add_argument("--output", "-o", default=None, help="Output file path")

    # Connection options
    parser.add_argument("--auth", "-a", default=None, help="user:password")
    parser.add_argument(
        "--verify", action=argparse.BooleanOptionalAction, default=True,
        help="SSL certificate verification",
    )
    parser.add_argument("--proxy", default=None, help="Proxy URL")
    parser.add_argument("--timeout", type=float, default=None, help="Request timeout in seconds")
    parser.add_argument(
        "--follow", action=argparse.BooleanOptionalAction, default=True,
        help="Follow redirects",
    )
    parser.add_argument("--max-redirects", type=int, default=30, help="Maximum number of redirects")

    # curl-cffi specific
    parser.add_argument(
        "--impersonate", "-i", default="chrome",
        help="Browser to impersonate",
    )

    return parser


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def handle_request(args, remaining):
    method, url, request_items = extract_positionals(remaining)
    parsed = parse_request_items(request_items)

    # Auto-detect method
    if method is None:
        method = "POST" if (parsed.data_fields or parsed.json_fields or parsed.files) else "GET"

    url = process_url(url)

    # Build headers
    headers = parsed.headers if parsed.headers else None

    # Query params
    params = parsed.query_params if parsed.query_params else None

    # Body
    data = None
    json_body = None

    if args.form or args.multipart:
        if parsed.data_fields:
            data = dict(parsed.data_fields)
    else:
        # JSON mode (default)
        if parsed.data_fields or parsed.json_fields:
            body = dict(parsed.data_fields)
            body.update(dict(parsed.json_fields))
            json_body = body

    # Files
    files = None
    if parsed.files:
        files = {}
        for field_name, filepath in parsed.files:
            files[field_name] = open(filepath, "rb")

    # Auth
    auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        auth = (parts[0], parts[1] if len(parts) > 1 else "")

    # Execute
    try:
        response = curl_cffi.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json_body,
            files=files,
            auth=auth,
            timeout=args.timeout,
            verify=args.verify,
            proxy=args.proxy,
            allow_redirects=args.follow,
            max_redirects=args.max_redirects,
            impersonate=args.impersonate,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        if files:
            for f in files.values():
                f.close()

    # Output
    print_spec = determine_print_spec(args)

    if args.download:
        # Print headers then download
        print_output(response, method, url, headers, None, "h")
        handle_download(response, url, args.output)
    else:
        request_body = None
        if json_body is not None:
            request_body = json.dumps(json_body, indent=2, ensure_ascii=False)
        elif data is not None:
            request_body = str(data)
        print_output(response, method, url, headers, request_body, print_spec)

    # Exit code based on status
    if response.status_code >= 400:
        sys.exit(1)


def main():
    parser = build_parser()
    args, remaining = parser.parse_known_args()

    if not remaining:
        parser.print_help()
        sys.exit(0)

    if remaining == ["doctor"]:
        print_doctor()
        return

    handle_request(args, remaining)


if __name__ == "__main__":
    main()
