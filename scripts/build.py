import json
import os
import platform
import shutil
import struct
import sys
import tempfile
from glob import glob
from pathlib import Path
from urllib.request import urlretrieve

from cffi import FFI

# this is the upstream libcurl-impersonate version
__version__ = "1.4.2"


def is_android_env() -> bool:
    return bool(
        sys.platform == "android"
        or os.environ.get("CIBW_PLATFORM") == "android"
        or os.environ.get("ANDROID_ROOT")
        or os.environ.get("ANDROID_DATA")
        or os.environ.get("TERMUX_VERSION")
    )


def detect_arch():
    with open(Path(__file__).parent.parent / "libs.json") as f:
        archs = json.loads(f.read())

    uname = platform.uname()
    uname_system = "Android" if is_android_env() else uname.system
    glibc_flavor = "gnueabihf" if uname.machine in ["armv7l", "armv6l"] else "gnu"

    libc, _ = platform.libc_ver()
    # https://github.com/python/cpython/issues/87414
    libc = glibc_flavor if libc == "glibc" else "musl"
    if is_android_env():
        libc = "android"
    pointer_size = struct.calcsize("P") * 8

    for arch in archs:
        if (
            arch["system"] == uname_system
            and arch["machine"] == uname.machine
            and arch["pointer_size"] == pointer_size
            and ("libc" not in arch or arch.get("libc") == libc)
        ):
            if arch.get("libdir"):
                arch["libdir"] = os.path.expanduser(arch["libdir"])
            else:
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
link_type = arch.get("link_type")
libdir = Path(arch["libdir"])
is_static = link_type == "static"
is_dynamic = link_type == "dynamic"
is_android = arch.get("libc") == "android"
print(f"Using {libdir} to store libcurl-impersonate")


def download_libcurl():
    expected = libdir / arch["obj_name"]
    if expected.exists():
        print(f"libcurl-impersonate: {expected} already downloaded.")
        return

    file = "libcurl-impersonate.tar.gz"
    sysname = "linux-" + arch["libc"] if arch["system"] == "Linux" else arch["sysname"]

    url = (
        f"https://github.com/lexiforest/curl-impersonate/releases/download/"
        f"v{__version__}/libcurl-impersonate-v{__version__}"
        f".{arch['arch']}-{sysname}.tar.gz"
    )

    print(f"Downloading libcurl-impersonate from {url}...")
    urlretrieve(url, file)

    print("Unpacking downloaded files...")
    os.makedirs(libdir, exist_ok=True)
    shutil.unpack_archive(file, libdir)

    if arch["system"] == "Windows":
        for file in glob(str(libdir / "lib/*.lib")):
            shutil.move(file, libdir)
        for file in glob(str(libdir / "bin/*.dll")):
            shutil.move(file, libdir)

    print("Files after unpacking:")
    print(os.listdir(libdir))


def get_curl_archives():
    print("Files in linking directory:")
    print(os.listdir(libdir))
    if is_static:
        # note that the order of libraries matters
        # https://stackoverflow.com/a/36581865
        return [str(libdir / arch["obj_name"])]
    else:
        return []


def get_curl_libraries():
    if arch["system"] == "Windows":
        return [
            "Crypt32",
            "Secur32",
            "wldap32",
            "Normaliz",
            "libcurl",
            "zstd",
            "zlib",
            "ssl",
            "nghttp2",
            "nghttp3",
            "ngtcp2",
            "ngtcp2_crypto_boringssl",
            "crypto",
            "brotlienc",
            "brotlidec",
            "brotlicommon",
            "iphlpapi",
        ]
    elif is_dynamic:
        return ["curl-impersonate"]
    else:
        return []


ffibuilder = FFI()
system = platform.system()
root_dir = Path(__file__).parent.parent
download_libcurl()

# With mega archive, we only have one to link
static_libs = get_curl_archives()
extra_link_args = []
if is_static:
    if system == "Darwin":
        extra_link_args = [
            f"-Wl,-force_load,{static_libs[0]}",
            "-lc++",
        ]
    elif system in ("Linux", "Android"):
        cxx_lib = "-lc++" if is_android else "-lstdc++"
        extra_link_args = [
            "-Wl,--whole-archive",
            static_libs[0],
            "-Wl,--no-whole-archive",
            cxx_lib,
        ]

libraries = get_curl_libraries()

ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    library_dirs=[str(libdir)],
    libraries=get_curl_libraries(),
    extra_objects=[],  # linked via extra_link_args
    source_extension=".c",
    include_dirs=[
        str(root_dir / "include"),
        str(root_dir / "ffi"),
        str(libdir / "include"),
    ],
    sources=[
        str(root_dir / "ffi/shim.c"),
    ],
    extra_compile_args=(
        ["-Wno-implicit-function-declaration"] if system == "Darwin" else []
    ),
    extra_link_args=extra_link_args,
)

with open(root_dir / "ffi/cdef.c") as f:
    cdef_content = f.read()
    ffibuilder.cdef(cdef_content)


if __name__ == "__main__":
    ffibuilder.compile(verbose=False)
