import os
import struct
import platform
from pathlib import Path

from cffi import FFI

ffibuilder = FFI()
# arch = "%s-%s" % (os.uname().sysname, os.uname().machine)
uname = platform.uname()


if uname.system == "Windows":
    if struct.calcsize("P") * 8 == 64:
        libdir = "./lib64"
    else:
        libdir = "./lib32"
elif uname.system == "Darwin":
    libdir = "/Users/runner/work/_temp/install/lib"
else:
    libdir = os.path.expanduser("~/.local/lib")

root_dir = Path(__file__).parent.parent

ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    libraries=["curl-impersonate-chrome"] if uname.system != "Windows" else ["libcurl"],
    library_dirs=[libdir],
    source_extension=".c",
    include_dirs=[
        str(root_dir / "curl_cffi/include"),
        str(root_dir / "ffi"),
    ],
    sources=[
        str(root_dir / "ffi/shim.c"),
    ],
    extra_compile_args=(
        ["-Wno-implicit-function-declaration"] if uname.system == "Darwin" else []
    ),
    # extra_link_args=["-Wl,-rpath,$ORIGIN/../libcurl/" + arch],
)

with open(root_dir / "ffi/cdef.c") as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
