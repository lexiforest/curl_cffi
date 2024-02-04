import json
import platform
import struct
from pathlib import Path

from cffi import FFI


def detect_arch():
    with open(Path(__file__).parent.parent / "libs.json") as f:
        archs = json.loads(f.read())
    uname = platform.uname()
    pointer_size = struct.calcsize("P") * 8
    for arch in archs:
        if (
            arch["system"] == uname.system
            and arch["machine"] == uname.machine
            and arch["pointer_size"] == pointer_size
        ):
            return arch
    raise Exception(f"Unsupported arch: {uname}")


ffibuilder = FFI()
system = platform.system()
root_dir = Path(__file__).parent.parent
arch = detect_arch()


ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    # FIXME from `curl-impersonate`
    libraries=["curl-impersonate-chrome"] if system != "Windows" else ["libcurl"],
    library_dirs=[arch["libdir"]],
    source_extension=".c",
    include_dirs=[
        str(root_dir / "include"),
        str(root_dir / "ffi"),
    ],
    sources=[
        str(root_dir / "ffi/shim.c"),
    ],
    extra_compile_args=(
        ["-Wno-implicit-function-declaration"] if system == "Darwin" else []
    ),
)

with open(root_dir / "ffi/cdef.c") as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
