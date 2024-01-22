import os
import struct
import platform

from cffi import FFI

ffibuilder = FFI()
# arch = "%s-%s" % (os.uname().sysname, os.uname().machine)
uname = platform.uname()
parent_dir = os.path.dirname(os.path.dirname(__file__))

if uname.system == "Windows":
    if struct.calcsize("P") * 8 == 64:
        libdir = "./lib64"
    else:
        libdir = "./lib32"
elif uname.system == "Darwin":
    if uname.machine == "x86_64":
        libdir = "/Users/runner/work/_temp/install/lib"
    else:
        libdir = "/usr/local/lib"
else:
    libdir = "/usr/local/lib"


ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    libraries=["curl-impersonate-chrome"] if uname.system != "Windows" else ["libcurl"],
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
        ["-Wno-implicit-function-declaration"] if uname.system == "Darwin" else []
    ),
    # extra_link_args=["-Wl,-rpath,$ORIGIN/../libcurl/" + arch],
)

with open(os.path.join(parent_dir, "ffi/cdef.c")) as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
