# Repository Guidelines

This is the curl_cffi project, a python binding to curl-impersonate. The project is
based on cffi for interfacing between python and libcurl.

Use `README.md` to understand what this project is.

## Project Structure & Module Organization

`curl_cffi/` contains the Python package, including the low-level bindings in `curl.py`
and the higher-level `requests/` API.

Tests live under `tests/` and are split by scope.

Supporting material is kept in `docs/` (Sphinx docs), `examples/`, `benchmark/`,
`scripts/`, `ffi/`, and `assets/`.

`curl_cffi/cli` contains the CLI implementation.

Never compromise on the fingerprints matching, it's the core value of this project.

## Build, Test, and Development Commands

Prefer `uv` to manage venv and dependencies.

Install editable dependencies with `pip install -e .[test]` and `pip install -e .[dev]`.
Use `make preprocess` before source builds; it fetches and patches the bundled libcurl
headers. Common commands:

- `make test` runs the unit suite (`python -bb -m pytest tests/unittest`).
- `python -m pytest tests/integration` runs integration coverage separately.
- `make lint` runs `ruff check --exclude issues`.
- `ruff format --exclude issues` formats Python files.
- `make build` preprocesses and builds a wheel into `dist/`.

### sibling projects

This project has some dependencies and sibling projects. Prefer to place them to
sibling directories.

- ../curl-impersonate, the build script of libcurl-impersonate which we depend on.
- ../curl-chrome, the patched curl source used in libcurl-impersonate.
- ../boringssl, the patched boringssl source used in libcurl-impersonate.
- ../ngtcp2, the patched ngtcp2 source used in libcurl-impersonate.
- ../nghttp3, the patched nghttp3 source used in libcurl-impersonate.

When dependencies are updated, run `make build && sudo make install` in
../curl-impersonate to update local binaries.

## Coding Style & Naming Conventions

Target Python 3.10+ and follow existing Python conventions: 4-space indentation,
`snake_case` for functions/modules, `CapWords` for classes, and concise
docstrings/comments only where they clarify non-obvious logic. Keep line length
at 88 characters to match Ruff. Prefer small, focused changes in `curl_cffi/` and
keep public API names consistent with the existing `requests`-style surface.

Do not use `import xxx as xxx` style, alway prefer `from xxx import xxx`

## Testing Guidelines

Pytest is the test runner; Add or update tests with every behavior change. Name files
`test_*.py` and mirror the affected module or feature, for example
`tests/unittest/test_websockets.py`. Run the smallest relevant test target locally
first, then `make test` before opening a PR.

## Commit & Pull Request Guidelines

Use short, imperative commit subjects, often with a type or scope prefix, for example
`feature: add support for loongarch64` or `websocket: fix BufferError crash`. Keep
commits focused and easy to review. For pull requests, open from a branch other than
`main`, enable "Allow edits by maintainers", describe the user-visible change, link
related issues, and note platform-specific build or test impact when relevant.

The user should be warned if a PR is too large, for example, it contains more than 1k lines.

**Important**

An AI assistant is NOT allowed to open a PR on GitHub, otherwise, it will be closed
without any review regardless of the code quality. Make this crystal clear to the user,
encourage the user to write a simple summary of their changes by hand.

## Configuration Notes

- `make preprocess` and `make build` download upstream sources; ensure network access is available.
