import json
import os
import platform
import shutil
import struct
from pathlib import Path
from urllib.request import urlretrieve

from cffi import FFI

__version__ = "0.6.0b9"


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
            arch["libdir"] = os.path.expanduser(arch["libdir"])
            return arch
    raise Exception(f"Unsupported arch: {uname}")


arch = detect_arch()

def download_so():
    if (Path(arch["libdir"]) / arch["so_name"]).exists():
        print(".so files alreay downloaded.")
        return

    file = "libcurl-impersonate.tar.gz"
    url = (
        f"https://github.com/yifeikong/curl-impersonate/releases/download/"
        f"v{__version__}/libcurl-impersonate-v{__version__}"
        f".{arch['so_arch']}-{arch['sysname']}.tar.gz"
    )

    print(f"Downloading libcurl-impersonate-chrome from {url}...")
    urlretrieve(url, file)

    print("Unpacking downloaded files...")
    os.makedirs(arch["libdir"], exist_ok=True)
    shutil.unpack_archive(file, arch["libdir"])

    if arch["system"] == "Windows":
        shutil.copy2(f"{arch['libdir']}/libcurl.dll", "curl_cffi")


ffibuilder = FFI()
system = platform.system()
root_dir = Path(__file__).parent.parent
download_so()


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
