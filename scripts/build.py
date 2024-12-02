import json
import os
import platform
import shutil
import struct
import tempfile
from pathlib import Path
from urllib.request import urlretrieve

from cffi import FFI

# this is the upstream libcurl-impersonate version
__version__ = "0.8.2"


def detect_arch():
    with open(Path(__file__).parent.parent / "libs.json") as f:
        archs = json.loads(f.read())

    uname = platform.uname()
    glibc_flavor = "gnueabihf" if uname.machine in ["armv7l", "armv6l"] else "gnu"

    libc, _ = platform.libc_ver()
    # https://github.com/python/cpython/issues/87414
    libc = glibc_flavor if libc == "glibc" else "musl"
    pointer_size = struct.calcsize("P") * 8

    for arch in archs:
        if (
            arch["system"] == uname.system
            and arch["machine"] == uname.machine
            and arch["pointer_size"] == pointer_size
            and ("libc" not in arch or arch.get("libc") == libc)
        ):
            if arch["libdir"]:
                arch["libdir"] = os.path.expanduser(arch["libdir"])
            else:
                global tmpdir
                if "CI" in os.environ:
                    tmpdir = "./tmplibdir"
                    os.makedirs(tmpdir, exist_ok=True)
                    arch["libdir"] = tmpdir
                else:
                    tmpdir = tempfile.TemporaryDirectory()
                    arch["libdir"] = tmpdir.name
            return arch
    raise Exception(f"Unsupported arch: {uname}")


arch = detect_arch()
print(f"Using {arch['libdir']} to store libcurl-impersonate")


def download_libcurl():
    if (Path(arch["libdir"]) / arch["so_name"]).exists():
        print(".so files already downloaded.")
        return

    file = "libcurl-impersonate.tar.gz"
    sysname = "linux-" + arch["libc"] if arch["system"] == "Linux" else arch["sysname"]

    url = (
        f"https://github.com/lexiforest/curl-impersonate/releases/download/"
        f"v{__version__}/libcurl-impersonate-v{__version__}"
        f".{arch['so_arch']}-{sysname}.tar.gz"
    )

    print(f"Downloading libcurl-impersonate-chrome from {url}...")
    urlretrieve(url, file)

    print("Unpacking downloaded files...")
    os.makedirs(arch["libdir"], exist_ok=True)
    shutil.unpack_archive(file, arch["libdir"])

    print("Files after unpacking")
    print(os.listdir(arch["libdir"]))


def get_curl_archives():
    print("Files for linking")
    print(os.listdir(arch["libdir"]))
    if arch["system"] == "Linux" and arch.get("link_type") == "static":
        # note that the order of libraries matters
        # https://stackoverflow.com/a/36581865
        return [
            f"{arch['libdir']}/libcurl-impersonate-chrome.a",
            f"{arch['libdir']}/libssl.a",
            f"{arch['libdir']}/libcrypto.a",
            f"{arch['libdir']}/libz.a",
            f"{arch['libdir']}/libzstd.a",
            f"{arch['libdir']}/libnghttp2.a",
            f"{arch['libdir']}/libbrotlidec.a",
            f"{arch['libdir']}/libbrotlienc.a",
            f"{arch['libdir']}/libbrotlicommon.a",
        ]
    else:
        return []


def get_curl_libraries():
    if arch["system"] == "Windows":
        return ["libcurl"]
    elif arch["system"] == "Darwin" or (
        arch["system"] == "Linux" and arch.get("link_type") == "dynamic"
    ):
        return ["curl-impersonate-chrome"]
    else:
        return []


ffibuilder = FFI()
system = platform.system()
root_dir = Path(__file__).parent.parent
download_libcurl()


ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    # FIXME from `curl-impersonate`
    libraries=get_curl_libraries(),
    extra_objects=get_curl_archives(),
    library_dirs=[arch["libdir"]],
    source_extension=".c",
    include_dirs=[
        str(root_dir / "include"),
        str(root_dir / "ffi"),
    ],
    sources=[
        str(root_dir / "ffi/shim.c"),
    ],
    extra_compile_args=(["-Wno-implicit-function-declaration"] if system == "Darwin" else []),
    extra_link_args=(["-lstdc++"]),
)

with open(root_dir / "ffi/cdef.c") as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
