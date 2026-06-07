# curl-cffi CLI — The Impersonated Web Fetch Skill

Use the `curl-cffi` CLI as a replacement for the `web_fetch` tool. It fetches
web pages with browser impersonation, bypassing TLS fingerprint-based blocking.
It supports HTTP/2 and HTTP/3 out of the box.

## When to use

- When `web_fetch` is unavailable or returns blocked/empty responses
- When a website requires a real browser TLS fingerprint
- When you need to fetch API endpoints, HTML pages, or JSON resources
- When you need to replay `.http` or `.har` files in batch

## Usage

```text
curl-cffi METHOD URL [REQUEST_ITEMS...] [FLAGS]
```

- **METHOD** is required: `get`, `post`, `put`, `delete`, `patch`, `head`, `options`, `trace`, `query` (case-insensitive).
- **URL** is required. Bare domains default to `https://`. A leading colon is a localhost shortcut (`:3000` → `http://localhost:3000`). An explicit port other than 443 uses `http://`.

## Basic usage

```bash
# Simple GET (impersonates Chrome by default)
curl-cffi get https://httpbin.org/get

# POST JSON data (`:=` for non-string values)
curl-cffi post https://httpbin.org/post name=John age:=30

# POST form data
curl-cffi post --form https://httpbin.org/post name=John

# Custom header
curl-cffi get https://httpbin.org/get X-My-Header:value

# Impersonate Safari instead of Chrome
curl-cffi get -i safari https://tls.browserleaks.com/json

# HTTP/3
curl-cffi get --http3 https://fp.impersonate.pro/api/http3

# Localhost shortcut
curl-cffi get :8000/api/health
```

## Output control

When connected to a terminal, default output includes response headers and body
with syntax highlighting. When piped, only the body is printed as plain text.

```bash
# Body only (good for piping/parsing)
curl-cffi get --body https://httpbin.org/get

# Headers only
curl-cffi get --headers https://httpbin.org/get

# Full verbose output (request + response headers and body)
curl-cffi post -v https://httpbin.org/post name=test

# Fine-grained: request headers + response headers only
curl-cffi get -p Hh https://httpbin.org/get
```

## Flags reference

| Flag | Short | Description |
|------|-------|-------------|
| `--body` | `-b` | Print response body only |
| `--headers` | | Print response headers only |
| `--verbose` | `-v` | Print full request + response |
| `--print` | `-p` | Fine-grained output: `H`(req headers) `B`(req body) `h`(resp headers) `b`(resp body) |
| `--impersonate` | `-i` | Browser to impersonate (default: `chrome`) |
| `--json` | `-j` | Serialize data as JSON (default) |
| `--form` | `-f` | Serialize data as form fields |
| `--multipart` | | Force multipart form data |
| `--auth` | `-a` | HTTP auth (`user:password`) |
| `--verify` / `--no-verify` | | Enable/disable SSL verification (default: enabled) |
| `--proxy` | | Proxy URL |
| `--timeout` | | Timeout in seconds |
| `--follow` / `--no-follow` | | Follow/don't follow redirects (default: follow) |
| `--max-redirects` | | Maximum number of redirects (default: 30) |
| `--download` | `-d` | Download response body to file |
| `--output` | `-o` | Output file path |
| `--http3` | | Use HTTP/3 |

## Request item syntax

| Syntax | Meaning | Example |
|--------|---------|---------|
| `Header:Value` | HTTP header | `Content-Type:application/json` |
| `Header:` | Remove header | `Accept:` |
| `param==value` | Query parameter | `page==2` |
| `field=value` | JSON/form string field | `name=John` |
| `field:=json` | JSON field (interpreted) | `age:=30` `tags:=["a","b"]` |
| `@filepath` | File upload | `@photo.jpg` |
| `+key=value` | Cookie | `+session=abc123` |

## Batch execution

The `run` subcommand executes multiple requests from a file:

```bash
# Run requests from an .http file (shared session by default)
curl-cffi run requests.http

# Replay a HAR file exported from Chrome DevTools
curl-cffi run session.har

# Independent requests (no shared cookies/connections)
curl-cffi run --no-session requests.http
```

Supported formats: `.http` / `.rest` (HTTP Request in Editor format) and `.har` (HTTP Archive).

## Diagnostics

```bash
curl-cffi doctor
```

Prints Python version, platform, curl_cffi version, and libcurl version.
