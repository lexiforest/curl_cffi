import os
from cffi import FFI


libraries = ["curl"]
if os.name == "nt":
	libraries = [
		"libcurl_a",
		"wldap32",
		"crypt32",
		"Ws2_32",
	]

def build_ffi(module_name="_curl_cffi"):
	ffi_builder = FFI()
	ffi_builder.set_source(module_name, r""" // passed to the real C compiler,
		#include "index.h"
	""", libraries=libraries, library_dirs=[], source_extension='.cpp', include_dirs=[
		os.path.join(os.path.dirname(__file__), "include"),
	], sources=[
		os.path.join(os.path.dirname(__file__), "include/index.cpp"),
	])

	with open("cdef.c", "r") as f:
		cdef_content = f.read()
		ffi_builder.cdef(cdef_content)
	return ffi_builder


ffibuilder = build_ffi()


def ffi_setup():
	return build_ffi("python_curl_cffi._curl_cffi")

if __name__ == "__main__":
	ffibuilder.compile(verbose=False)
