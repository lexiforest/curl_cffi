import argparse
import os
import sys

from .doctor import print_doctor
from .pro import add_pro_parsers, handle_pro_command
from .run import handle_run, parse_http_file  # noqa: F401
from .parse import (  # noqa: F401
    SUPPORTED_METHODS,
    ParsedItems,
    parse_request_items,
    process_url,
)
from .request import handle_request

__all__ = [
    "build_parser",
    "main",
    "handle_request",
    "handle_run",
    "handle_pro_command",
    "add_pro_parsers",
    "parse_http_file",
    "parse_request_items",
    "process_url",
    "print_doctor",
    "SUPPORTED_METHODS",
    "ParsedItems",
]


def _add_common_flags(parser: argparse.ArgumentParser) -> None:
    """Add flags shared by all HTTP verb subcommands."""
    content_group = parser.add_mutually_exclusive_group()
    content_group.add_argument(
        "--json",
        "-j",
        action="store_true",
        dest="json_mode",
        help="(default) Serialize data items as a JSON object",
    )
    content_group.add_argument(
        "--form",
        "-f",
        action="store_true",
        help="Serialize data items as form fields",
    )
    content_group.add_argument(
        "--multipart",
        action="store_true",
        help="Force multipart form data",
    )

    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--headers",
        action="store_true",
        dest="headers_only",
        help="Print response headers only",
    )
    output_group.add_argument(
        "--body",
        action="store_true",
        dest="body_only",
        help="Print response body only",
    )
    output_group.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print request and response headers and body",
    )
    output_group.add_argument(
        "--print",
        "-p",
        dest="print_spec",
        default=None,
        help="Output control: H(req headers) B(req body) h(resp headers) b(resp body)",
    )

    parser.add_argument(
        "--download",
        "-d",
        action="store_true",
        help="Download response body to file",
    )
    parser.add_argument("--output", "-o", default=None, help="Output file path")

    parser.add_argument("--auth", "-a", default=None, help="user:password")
    parser.add_argument(
        "--verify",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="SSL certificate verification",
    )
    parser.add_argument("--proxy", default=None, help="Proxy URL")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Request timeout in seconds",
    )
    parser.add_argument(
        "--follow",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Follow redirects",
    )
    parser.add_argument(
        "--max-redirects",
        type=int,
        default=30,
        help="Maximum number of redirects",
    )

    parser.add_argument(
        "--impersonate",
        "-i",
        default="chrome",
        help="Browser to impersonate",
    )

    http_version_group = parser.add_mutually_exclusive_group()
    http_version_group.add_argument(
        "--http1.1",
        action="store_const",
        const="v1",
        dest="http_version",
        help="Use HTTP/1.1",
    )
    http_version_group.add_argument(
        "--http2",
        action="store_const",
        const="v2",
        dest="http_version",
        help="Use HTTP/2",
    )
    http_version_group.add_argument(
        "--http3",
        action="store_const",
        const="v3",
        dest="http_version",
        help="Use HTTP/3",
    )
    http_version_group.add_argument(
        "--http3-only",
        action="store_const",
        const="v3only",
        dest="http_version",
        help="Use HTTP/3 only (no fallback to HTTP/2 or HTTP/1.1)",
    )


def _add_request_positionals(parser: argparse.ArgumentParser) -> None:
    """Add URL and request items positional args."""
    parser.add_argument("url", metavar="URL", help="Request URL")
    parser.add_argument(
        "items",
        metavar="ITEM",
        nargs="*",
        help=(
            "Request items: Header:Value, param==value, field=value, field:=json, "
            "@file, +cookie=value"
        ),
    )


def _print_help() -> None:
    prog = os.path.basename(sys.argv[0])
    if prog in ("__main__.py", "-m"):
        prog = "curl-cffi"
    print(f"""\
Usage: {prog} <command> [options]

HTTP request CLI with browser impersonation.

HTTP verbs:
  get, post, put, delete, patch    Make an HTTP request
  head, options, trace, query      (case-insensitive)

Request items (for HTTP verb commands):
  Header:Value   HTTP header
  param==value   Query parameter
  field=value    Data field
  field:=json    Raw JSON field
  @file          File upload
  +key=value     Cookie

Tools:
  run FILE                         Run requests from .http or .har file
  doctor                           Dump diagnostic information

Fingerprints:
  update                           Update local fingerprints cache
  list                             List local and native fingerprints
  config                           Configure API access for Pro fingerprints

Run '{prog} <command> --help' for details on a specific command.""")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="curl-cffi",
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="store_true", dest="show_help")

    subparsers = parser.add_subparsers(dest="command")

    for method in sorted(SUPPORTED_METHODS):
        for name in (method.lower(), method):
            sub = subparsers.add_parser(
                name,
                description=f"Make an HTTP {method} request.",
            )
            _add_request_positionals(sub)
            _add_common_flags(sub)
            sub.set_defaults(method=method)

    sub = subparsers.add_parser(
        "doctor",
        description="Dump diagnostic information for debugging.",
    )
    sub.set_defaults(method=None)

    add_pro_parsers(subparsers)

    sub = subparsers.add_parser(
        "run",
        description="""\
Run requests from a file.

Supported formats (auto-detected by extension):
  .http / .rest   HTTP Request in Editor format
  .har            HAR (HTTP Archive) format

HTTP file format:
  ### (request separator)
  POST http://example.com/api
  Content-Type: application/json

  {"key": "value"}
  ###
  GET http://example.com

Har file:
  Chrome exported HAR files do not contain cookies and auth headers by default. To include them:

  In DevTools settings: Gear Icon -> Preferences -> Network -> select "Allow to generate HAR with sensitive data"
""",  # noqa: E501
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub.add_argument("file", metavar="FILE", help="Path to .http or .har file")
    sub.add_argument(
        "--session",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Use a single session for all requests, sharing cookies and connections "
            "(default: enabled)"
        ),
    )
    _add_common_flags(sub)
    sub.set_defaults(method=None)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None or getattr(args, "show_help", False):
        _print_help()
        sys.exit(0)

    if args.command == "doctor":
        print_doctor()
        return

    if handle_pro_command(args):
        return

    if args.command == "run":
        handle_run(args)
        return

    handle_request(args, args.method)
