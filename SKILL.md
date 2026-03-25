# curl-cffi CLI — Web Fetch Skill

Use the `curl-cffi` CLI as a replacement for the `web_fetch` tool. It fetches
web pages with browser impersonation, bypassing TLS fingerprint-based blocking.

## When to use

- When `web_fetch` is unavailable or returns blocked/empty responses
- When a website requires a real browser TLS fingerprint
- When you need to fetch API endpoints, HTML pages, or JSON resources

## Basic usage

```bash
# Fetch a page (HTTPS by default, impersonates Chrome)
curl-cffi https://example.com

# Body only, no headers (good for piping/parsing)
curl-cffi --body https://example.com

# Fetch JSON API
curl-cffi https://api.example.com/data

# POST JSON data
curl-cffi POST https://api.example.com/submit name=value key:=123

# Custom headers
curl-cffi https://example.com Authorization:Bearer\ token123

# Impersonate a different browser
curl-cffi -i safari https://example.com
```

## Extracting content

```bash
# Get just the response body as plain text (suitable for LLM consumption)
curl-cffi --body https://example.com

# Get JSON response
curl-cffi --body https://api.example.com/data.json

# Verbose: see request and response headers + body
curl-cffi -v https://example.com
```

## Flags reference

| Flag | Short | Description |
|------|-------|-------------|
| `--body` | `-b` | Print response body only |
| `--headers` | | Print response headers only |
| `--verbose` | `-v` | Print full request + response |
| `--impersonate` | `-i` | Browser to impersonate (default: `chrome`) |
| `--form` | `-f` | Send form-encoded data |
| `--auth` | `-a` | HTTP auth (`user:password`) |
| `--no-verify` | | Skip SSL verification |
| `--proxy` | | Proxy URL |
| `--timeout` | | Timeout in seconds |
| `--download` | `-d` | Save response to file |
| `--output` | `-o` | Output file path |

## Request item syntax

| Syntax | Meaning |
|--------|---------|
| `Header:Value` | Set HTTP header |
| `param==value` | Query parameter |
| `field=value` | String data field |
| `field:=json` | Raw JSON data field |
| `@filepath` | File upload |
