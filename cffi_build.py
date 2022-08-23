import os

from cffi import FFI

ffibuilder = FFI()

ffibuilder.set_source(
    "curl_cffi._curl_cffi",
    """#include "index.h"
    """,
    libraries=["curl"],
    library_dirs=[
        os.path.join(os.path.dirname(__file__), "lib"),
    ],
    source_extension=".c",
    include_dirs=[
        os.path.join(os.path.dirname(__file__), "include"),
    ],
    sources=[
        os.path.join(os.path.dirname(__file__), "include/index.c"),
    ],
)

with open(os.path.join(os.path.dirname(__file__), "cdef.c")) as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
