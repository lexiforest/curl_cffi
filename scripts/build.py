import os
import platform
import shutil
import sys
import tempfile
from glob import glob
from pathlib import Path
from urllib.request import urlretrieve

from cffi import FFI

# this is the upstream libcurl-impersonate version
__version__ = "2.0.0a5"

# Architecture mappings: machine -> arch name
ARCH_MAP = {
    "x86_64": "x86_64",
    "AMD64": "x86_64",
    "i686": "i386",
    "ARM64": "arm64",
    "arm64": "arm64",
    "aarch64": "aarch64",
    "riscv64": "riscv64",
    "loongarch64": "loongarch64",
    "armv6l": "arm",
    "armv7l": "arm",
    "armv8l": "arm",
}

# Pointer size by machine (32-bit architectures)
POINTER_SIZE_32 = {"i686", "armv6l", "armv7l"}

# System name mappings
SYSNAME_MAP = {
    "Windows": "win32",
    "Darwin": "macos",
    "Linux": "linux",
    "Android": "linux-android",
}


def is_android_env() -> bool:
    return bool(
        sys.platform == "android"
        or os.environ.get("CIBW_PLATFORM") == "android"
        or os.environ.get("ANDROID_ROOT")
        or os.environ.get("ANDROID_DATA")
        or os.environ.get("TERMUX_VERSION")
    )


def detect_arch():
    uname = platform.uname()
    machine = uname.machine
    system = "Android" if is_android_env() else uname.system

    if machine not in ARCH_MAP:
        raise Exception(f"Unsupported arch: {uname}")

    arch = ARCH_MAP[machine]
    pointer_size = 32 if machine in POINTER_SIZE_32 else 64
    obj_name = (
        "libcurl-impersonate.dll" if system == "Windows" else "libcurl-impersonate.a"
    )
    link_type = "dynamic" if system == "Windows" else "static"
    sysname = SYSNAME_MAP.get(system)

    if system == "Android":
        libc = "android"
    else:
        glibc_flavor = "gnueabihf" if machine in ("armv7l", "armv6l") else "gnu"
        detected_libc, _ = platform.libc_ver()
        libc = glibc_flavor if detected_libc == "glibc" else "musl"

    if system == "Windows":
        libdir_map = {
            ("AMD64", 64): "./lib64",
            ("AMD64", 32): "./lib32",
            ("ARM64", 64): "./libarm64",
        }
        libdir = libdir_map.get((machine, pointer_size))
    else:
        if "CI" in os.environ:
            libdir = "./tmplibdir"
            os.makedirs(libdir, exist_ok=True)
        else:
            libdir = tempfile.mkdtemp()

    if libdir:
        libdir = os.path.expanduser(libdir)

    return {
        "system": system,
        "machine": machine,
        "pointer_size": pointer_size,
        "libdir": libdir,
        "sysname": sysname,
        "link_type": link_type,
        "obj_name": obj_name,
        "arch": arch,
        "libc": libc,
    }


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
            src = Path(file)
            dst = libdir / src.name
            if dst.exists():
                dst.unlink()
            shutil.move(src, dst)
        for file in glob(str(libdir / "lib/*.dll")):
            src = Path(file)
            dst = libdir / src.name
            if dst.exists():
                dst.unlink()
            shutil.move(src, dst)

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
            "libcurl-impersonate_imp",
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
