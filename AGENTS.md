# curl_cffi

## Setup commands


- stable: `pip install curl_cffi`
- beta: `pip install curl_cffi --pre`
 
## Code style
- Use the black format, with max line length: 88.
- Current supported version: Python 3.10 and above, do not use Python 3.9 syntax.

## Development

We use conda to create and manage virtual environment, to activate:

    conda activate curl_cffi

After each edit, run `make lint` to find style issues, use `ruff check --fix .` to fix
most of them. If there are still issues, try to fix them if it's safe to fix. If it's
still not fixed, pop up and let me know.

## Testing

## PR instructions
- Always run `make test` and `make lint` before committing.
- Make sure you added a unittest for your PR.
