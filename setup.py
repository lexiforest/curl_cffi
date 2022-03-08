import os
import sys
from setuptools import setup


def do_setup():
	# os.chdir(os.path.dirname(__file__))

	if "_cffi_backend" in sys.builtin_module_names:
		# pypy has cffi bundled
		import _cffi_backend
		requires_cffi = "cffi==" + _cffi_backend.__version__
	else:
		requires_cffi = "cffi>=1.0.0"

	if requires_cffi.startswith("cffi==0."):
		# Existing cffi version present
		from cffi_build import ffibuilder
		ext_config = ffibuilder.verifier.get_extension()
		ext_config.name = "python_curl_cffi._curl_cffi"
		extra_args = {
			"setup_requires": [requires_cffi],
			"ext_modules": [ext_config],
		}
	else:
		extra_args = {
			"setup_requires": [requires_cffi],
			"cffi_modules": ["cffi_build.py:ffi_setup"]
		}

	setup(
		name='python-curl-cffi',
		version='0.1.0',
		author='Nicholas Kwan',
		description="libcurl ffi bindings for Python",
		url="https://bitbucket.org/multippt/python_curl_cffi",
		package_dir={"python_curl_cffi": "."},
		packages=['python_curl_cffi'],
		**extra_args
	)


if __name__ == "__main__":
	do_setup()
