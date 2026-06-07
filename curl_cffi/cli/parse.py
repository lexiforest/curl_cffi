import json
import sys
from dataclasses import dataclass, field

SUPPORTED_METHODS = {
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "OPTIONS",
    "HEAD",
    "TRACE",
    "PATCH",
    "QUERY",
}


def process_url(url: str) -> str:
    """Normalise a URL: localhost shortcut, default scheme."""
    if url.startswith(":"):
        return f"http://localhost{url}"
    if "://" not in url:
        # Extract host part to check for an explicit port
        host_part = url.split("/", 1)[0]
        if ":" in host_part:
            port = host_part.rsplit(":", 1)[1]
            scheme = "https" if port == "443" else "http"
        else:
            scheme = "https"
        return f"{scheme}://{url}"
    return url


@dataclass
class ParsedItems:
    headers: dict[str, str] = field(default_factory=dict)
    headers_to_remove: list[str] = field(default_factory=list)
    query_params: list[tuple[str, str]] = field(default_factory=list)
    data_fields: list[tuple[str, str]] = field(default_factory=list)
    json_fields: list[tuple[str, object]] = field(default_factory=list)
    files: list[tuple[str, str]] = field(default_factory=list)
    cookies: dict[str, str] = field(default_factory=dict)


def parse_request_items(items: list[str]) -> ParsedItems:
    """Parse request items into structured data."""
    result = ParsedItems()
    for item in items:
        if item.startswith("+") and "=" in item[1:]:
            key, _, value = item[1:].partition("=")
            result.cookies[key] = value
        elif ":=" in item:
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
