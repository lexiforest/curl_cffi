import os

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
        "/usr/local/lib" if os.uname().sysname == "Linux" else
        "/Users/runner/work/_temp/install/lib" if os.uname().sysname == "Darwin" else ""
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
