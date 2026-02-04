# curl_cffi

## Setup commands


- stable: `pip install curl_cffi`
- beta: `pip install curl_cffi --pre`
 
## Code style
- Use the black format, with max line length: 88.
- Current supported version: Python 3.10 and above, do not use Python 3.9 syntax.

## Dev environment tips

We use conda to create and manage virtual environment, to activate:

    conda activate curl_cffi

## Testing instructions

## PR instructions
- Always run `make test` and `make lint` before committing.
- Make sure you added a unittest for your PR.
