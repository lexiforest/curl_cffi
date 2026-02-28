# Repository Guidelines

## Project Structure & Module Organization
- `curl_cffi/` contains the Python package, including the requests-like API (`curl_cffi/requests/`), async helpers (`aio.py`), and compiled bindings (`_wrapper.*`).
- `ffi/` and `include/` hold CFFI build inputs and generated headers from libcurl-impersonate.
- `tests/` is split into `unittest/`, `integration/`, `threads/`, and `pro/` suites.
- `docs/`, `examples/`, and `benchmark/` host documentation, usage samples, and performance scripts.
- `scripts/` includes build and maintenance utilities.

## Build, Test, and Development Commands
- `make preprocess`: download and patch libcurl-impersonate sources; generates headers in `include/`.
- `make install-editable`: install the package in editable mode for local iteration.
- `make build`: build a wheel (runs preprocessing first).
- `make lint`: run `ruff` checks (excludes `issues/`).
- `make format`: auto-format with `ruff format` (excludes `issues/`).
- `make test` or `python -bb -m pytest tests/unittest`: run the unit test suite.

## Coding Style & Naming Conventions
- Python, 4-space indentation, PEP 8 conventions.
- Formatting and linting are enforced with `ruff`; line length is 88.
- Imports follow `isort`’s `black` profile.
- Module and function names use `snake_case`; tests are named `test_*.py` with `test_*` functions.

## Testing Guidelines
- Tests use `pytest` with async helpers (`pytest-asyncio`, `pytest-trio`).
- Install test deps with `pip install -e .[test]` or `pip install -e .[dev]`.
- Add unit tests under `tests/unittest/` unless the change clearly belongs in `integration/` or `threads/`.

## Commit & Pull Request Guidelines
- Commit messages are short, imperative summaries and often include a PR number, e.g., `Update docs (#705)`.
- PRs should include a clear description, linked issues when applicable, and the tests/commands run.
- Include benchmark notes when changing performance-sensitive code (e.g., `curl.py`, `_wrapper` bindings).

## Configuration Notes
- `make preprocess` and `make build` download upstream sources; ensure network access is available.
- If you use a custom libcurl build, be prepared to set relevant library paths (for example, `LD_LIBRARY_PATH`).
