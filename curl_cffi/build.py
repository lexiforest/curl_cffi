import os
import platform
import struct

from cffi import FFI


def abs_machine():
    machine = platform.machine()

    pointer_bits = struct.calcsize("P") * 8
    if pointer_bits not in (32, 64):
        raise Exception("Unsupported pointer size")

    is_64 = pointer_bits == 64

    # x86 based archs
    if machine in ('AMD64', 'x86_64', 'i686'):
        return "x86_64" if is_64 else "i686"
    # arm based archs
    elif machine in ('aarch64', 'arm64', 'armv6l', 'armv7l'):
        return "aarch64" if is_64 else "arm"
    else:
        raise Exception("Unsupported processor")


ffibuilder = FFI()
system = platform.system()
machine = abs_machine()
parent_dir = os.path.dirname(os.path.dirname(__file__))

if system == "Windows":
    if machine == "x86_64":
        libdir = "./lib32"
    elif machine == "i686":
        libdir = "./lib64"
    else:
        libdir = "ERROR"
elif system == "Darwin":
    if machine in ("x86_64", "aarch64"):
        libdir = "/Users/runner/work/_temp/install/lib"
    else:
        libdir = "ERROR"
else:
    if machine in ("x86_64", "arm", "aarch64"):
        libdir = os.path.expanduser("~/.local/lib")
    else:
        libdir = "ERROR"

if libdir == "ERROR":
    raise Exception("Unsupported platform")

ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    # FIXME from `curl-impersonate`
    libraries=["curl-impersonate-chrome"] if system != "Windows" else ["libcurl"],
    library_dirs=[libdir],
    source_extension=".c",
    include_dirs=[
        os.path.join(parent_dir, "include"),
        os.path.join(parent_dir, "ffi"),
    ],
    sources=[
        os.path.join(parent_dir, "ffi/shim.c"),
    ],
    extra_compile_args=(
        ["-Wno-implicit-function-declaration"] if system == "Darwin" else []
    ),
)

with open(os.path.join(parent_dir, "ffi/cdef.c")) as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
