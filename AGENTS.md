# Repository Guidelines

This is the curl_cffi project, a python binding to curl-impersonate. The project is based
on cffi for interfacing between python and libcurl.

## Project Structure & Module Organization

`curl_cffi/` contains the Python package, including the low-level bindings in `curl.py` and the higher-level `requests/` API. Tests live under `tests/` and are split by scope: `tests/unittest/`, `tests/integration/`, and `tests/threads/`. Supporting material is kept in `docs/` (Sphinx docs), `examples/`, `benchmark/`, `scripts/`, `ffi/`, and `assets/`.

`curl_cffi/cli` contains the CLI implementation.

## Build, Test, and Development Commands

Install editable dependencies with `pip install -e .[test]` and `pip install -e .[dev]`. Use `make preprocess` before source builds; it fetches and patches the bundled libcurl headers. Common commands:

- `make test` runs the unit suite (`python -bb -m pytest tests/unittest`).
- `python -m pytest tests/integration` runs integration coverage separately.
- `make lint` runs `ruff check --exclude issues`.
- `ruff format --exclude issues` formats Python files.
- `make build` preprocesses and builds a wheel into `dist/`.

## Coding Style & Naming Conventions

Target Python 3.10+ and follow existing Python conventions: 4-space indentation, `snake_case` for functions/modules, `CapWords` for classes, and concise docstrings/comments only where they clarify non-obvious logic. Keep line length at 88 characters to match Ruff. Prefer small, focused changes in `curl_cffi/` and keep public API names consistent with the existing `requests`-style surface.

## Testing Guidelines

Pytest is the test runner; async coverage uses `pytest-asyncio` and `pytest-trio`. Add or update tests with every behavior change. Name files `test_*.py` and mirror the affected module or feature, for example `tests/unittest/test_websockets.py`. Run the smallest relevant test target locally first, then `make test` before opening a PR.

## Commit & Pull Request Guidelines

Recent history favors short, imperative commit subjects, often with a type or scope prefix, for example `feat: add support for loongarch64` or `ws: fix BufferError crash`. Keep commits focused and easy to review. For pull requests, open from a branch other than `main`, enable "Allow edits by maintainers", describe the user-visible change, link related issues, and note platform-specific build or test impact when relevant.

## Configuration Notes
- `make preprocess` and `make build` download upstream sources; ensure network access is available.
