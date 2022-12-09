from setuptools import setup

# this option is only valid in setup.py
setup(
    cffi_modules=["curl_cffi/build.py:ffibuilder"],
)
