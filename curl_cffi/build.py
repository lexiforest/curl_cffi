import os
import platform

from cffi import FFI

ffibuilder = FFI()
# arch = "%s-%s" % (os.uname().sysname, os.uname().machine)


ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    libraries=["curl-impersonate-chrome"],
    library_dirs=[
        "/usr/local/lib" if platform.uname().system == "Linux" else
        "/Users/runner/work/_temp/install/lib" if platform.uname().system == "Darwin" else
        "./lib"
    ],
    source_extension=".c",
    include_dirs=[
        os.path.join(os.path.dirname(__file__), "include"),
    ],
    sources=[
        os.path.join(os.path.dirname(__file__), "shim.c"),
    ],
    # extra_link_args=["-Wl,-rpath,$ORIGIN/../libcurl/" + arch],
)

with open(os.path.join(os.path.dirname(__file__), "cdef.c")) as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
