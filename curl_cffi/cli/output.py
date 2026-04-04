from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Literal

from curl_cffi.const import CurlHttpVersion
from curl_cffi.requests import Response

from rich.console import Console
from rich.progress import Progress, BarColumn, DownloadColumn, TransferSpeedColumn
from rich.syntax import Syntax
from rich.text import Text


def _http_ver_label(response: Response) -> Literal["1.0", "1.1", "2", "3"]:
    mapping = {
        CurlHttpVersion.V1_0: "1.0",
        CurlHttpVersion.V1_1: "1.1",
        CurlHttpVersion.V2_0: "2",
        CurlHttpVersion.V2TLS: "2",
        CurlHttpVersion.V2_PRIOR_KNOWLEDGE: "2",
        CurlHttpVersion.V3: "3",
        CurlHttpVersion.V3ONLY: "3",
    }
    return mapping.get(response.http_version, "1.1")  # type: ignore


def determine_print_spec(args: argparse.Namespace) -> str:
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
    if sys.stdout.isatty():  # interactive terminal
        return "hb"
    return "b"


def _print_headers(console: Console, lines: list[str], use_color: bool) -> None:
    """Print HTTP headers, with rich colors when possible."""
    if not use_color:
        for line in lines:
            print(line)
        return
    for line in lines:
        if ": " in line:
            key, _, value = line.partition(": ")
            text = Text()
            text.append(key, style="bold cyan")
            text.append(": ", style="dim")
            text.append(value)
            console.print(text)
        else:
            console.print(Text(line, style="bold green"))


def _print_body(console: Console, response: Response, use_color: bool) -> None:
    """Print response body, with syntax highlight when possible."""
    content_type = response.headers.get("content-type", "")
    if "json" in content_type:
        try:
            formatted = json.dumps(response.json(), indent=2, ensure_ascii=False)
            if use_color:
                console.print(
                    Syntax(
                        formatted,
                        "json",
                        theme="ansi_dark",
                        word_wrap=True,
                        background_color="default",
                    )
                )
            else:
                print(formatted)
            return
        except (json.JSONDecodeError, ValueError):
            pass
    if content_type.startswith("image/"):
        print(
            f"Binary image data ({content_type}, {len(response.content)} bytes)",
            file=sys.stderr,
        )
        return
    if not use_color:
        print(response.text)
        return
    if "html" in content_type:
        console.print(
            Syntax(
                response.text,
                "html",
                theme="ansi_dark",
                word_wrap=True,
                background_color="default",
            )
        )
    elif "xml" in content_type:
        console.print(
            Syntax(
                response.text,
                "xml",
                theme="ansi_dark",
                word_wrap=True,
                background_color="default",
            )
        )
    else:
        console.print(response.text, highlight=False, markup=False)


def _print_status(console: Console, response: Response, use_color: bool) -> None:
    """Print the HTTP status line."""
    ver = _http_ver_label(response)
    status_line = f"HTTP/{ver} {response.status_code} {response.reason}"
    if not use_color:
        print(status_line)
        return
    if response.status_code < 300:
        style = "bold green"
    elif response.status_code < 400:
        style = "bold yellow"
    else:
        style = "bold red"
    console.print(Text(status_line, style=style))


def print_output(
    response: Response,
    method: str,
    url: str,
    request_headers: dict[str, str] | None,
    request_body: str | None,
    print_spec: str,
) -> None:
    use_color = sys.stdout.isatty()  # interactive terminal
    console = Console(force_terminal=use_color, no_color=not use_color)

    # print request headers
    if "H" in print_spec:
        lines = [f"{method} {url}"]
        for k, v in (request_headers or {}).items():
            lines.append(f"{k}: {v}")
        _print_headers(console, lines, use_color)
        print()

    # print request body
    if "B" in print_spec and request_body:
        if use_color:
            console.print(
                Syntax(
                    request_body,
                    "json",
                    theme="ansi_dark",
                    word_wrap=True,
                    background_color="default",
                )
            )
        else:
            print(request_body)
        print()

    # print response headers
    if "h" in print_spec:
        _print_status(console, response, use_color)
        header_lines = [f"{k}: {v}" for k, v in response.headers.items()]
        _print_headers(console, header_lines, use_color)
        print()

    # print response body
    if "b" in print_spec:
        _print_body(console, response, use_color)


def _sanitize_filename(name: str) -> str:
    """Remove or replace characters unsafe for filenames."""
    # Strip directory traversal and null bytes
    name = name.replace("\x00", "").split("/")[-1].split("\\")[-1]
    # Keep only safe characters
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "download"


def handle_download(
    response: Response, url: str, output_path: str | None = None
) -> None:
    if output_path is None:
        cd = response.headers.get("content-disposition", "")
        if "filename=" in cd:
            output_path = cd.split("filename=")[1].strip('"').strip("'")
        else:
            output_path = url.rstrip("/").split("/")[-1] or "download"
    output_path = _sanitize_filename(output_path)

    content = response.content
    total = len(content)
    console = Console(stderr=True)
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(output_path, total=total)
        with open(output_path, "wb") as f:
            chunk_size = 64 * 1024
            for offset in range(0, total, chunk_size):
                chunk = content[offset : offset + chunk_size]
                f.write(chunk)
                progress.advance(task, len(chunk))
    print(f"Downloaded to {output_path}", file=sys.stderr)
