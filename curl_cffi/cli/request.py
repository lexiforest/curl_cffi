from __future__ import annotations

import argparse
import json
import sys
from io import BufferedReader
from typing import Any

import curl_cffi
from curl_cffi.requests import Session

from .output import determine_print_spec, handle_download, print_output
from .parse import parse_request_items, process_url


def _execute_request(
    args: argparse.Namespace,
    method: str,
    url: str,
    headers: dict[str, str] | None = None,
    params: list[tuple[str, str]] | None = None,
    data: dict[str, str] | str | None = None,
    json_body: dict[str, Any] | None = None,
    files: dict[str, BufferedReader] | None = None,
    cookies: dict[str, str] | None = None,
    auth: tuple[str, str] | None = None,
    session: Session | None = None,
) -> int:
    """Execute a single HTTP request and handle output.

    Returns:
        0 on success, 1 on error."""
    request_fn = session.request if session else curl_cffi.request
    try:
        response = request_fn(
            method=method,
            url=url,
            headers=headers,
            params=params,
            data=data,
            json=json_body,
            files=files,
            cookies=cookies,
            auth=auth,
            timeout=args.timeout,
            verify=args.verify,
            proxy=args.proxy,
            allow_redirects=args.follow,
            max_redirects=args.max_redirects,
            impersonate=args.impersonate,
            http_version=getattr(args, "http_version", None),
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        if files:
            for f in files.values():
                f.close()

    print_spec = determine_print_spec(args)

    if args.download:
        print_output(response, method, url, headers, None, "h")
        handle_download(response, url, args.output)
    else:
        request_body = None
        if json_body is not None:
            request_body = json.dumps(json_body, indent=2, ensure_ascii=False)
        elif data is not None:
            request_body = str(data)
        print_output(response, method, url, headers, request_body, print_spec)

    if response.status_code >= 400:
        return 1
    return 0


def handle_request(
    args: argparse.Namespace, method: str, exit_on_error: bool = True
) -> int:
    """Entrypoint for building and executing a request from parsed args.

    Returns:
        0 on success, 1 on error."""
    url = process_url(args.url)
    parsed = parse_request_items(args.items)

    data = None
    json_body = None

    if args.form or args.multipart:
        if parsed.data_fields:
            data = dict(parsed.data_fields)
    else:
        if parsed.data_fields or parsed.json_fields:
            body = dict(parsed.data_fields)
            body.update(dict(parsed.json_fields))
            json_body = body

    files = None
    if parsed.files:
        files = {}
        for field_name, filepath in parsed.files:
            files[field_name] = open(filepath, "rb")  # noqa: SIM115

    auth = None
    if args.auth:
        parts = args.auth.split(":", 1)
        auth = (parts[0], parts[1] if len(parts) > 1 else "")

    rc = _execute_request(
        args,
        method,
        url,
        headers=parsed.headers,
        params=parsed.query_params,
        data=data,
        json_body=json_body,
        files=files,
        cookies=parsed.cookies,
        auth=auth,
    )
    if rc != 0 and exit_on_error:
        sys.exit(1)
    return rc
