import os
import platform
import shutil
import sys
import tempfile
import time
from glob import glob
from http.client import HTTPException
from pathlib import Path
from urllib.request import urlretrieve

from cffi import FFI

# this is the upstream libcurl-impersonate version
__version__ = "2.1.1"

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

    if build_dir := os.environ.get("IMPERSONATE_BUILD_DIR"):
        libdir = os.path.expanduser(build_dir)
    elif system == "Windows":
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


def get_link_type(arch):
    link_type = os.environ.get("IMPERSONATE_LINK_TYPE", arch.get("link_type"))
    if link_type not in ("static", "dynamic"):
        raise ValueError(
            "IMPERSONATE_LINK_TYPE must be either 'static' or 'dynamic', "
            f"not {link_type!r}"
        )
    return link_type


def get_obj_name(arch, link_type):
    if link_type == arch.get("link_type"):
        return arch["obj_name"]
    if link_type == "static":
        if arch["system"] == "Windows":
            raise ValueError("Static linking is not supported on Windows")
        return "libcurl-impersonate.a"
    if arch["system"] == "Darwin":
        return "libcurl-impersonate.dylib"
    if arch["system"] == "Linux":
        return "libcurl-impersonate.so"
    return "libcurl-impersonate.dll"


arch = detect_arch()
link_type = get_link_type(arch)
obj_name = get_obj_name(arch, link_type)
libdir = Path(arch["libdir"])
is_static = link_type == "static"
is_dynamic = link_type == "dynamic"
is_android = arch.get("libc") == "android"
print(f"Using {libdir} to store libcurl-impersonate")


def download_libcurl():
    expected = libdir / obj_name
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
    retries = 3
    for attempt in range(1, retries + 1):
        try:
            urlretrieve(url, file)
            break
        except (OSError, HTTPException) as e:
            if attempt == retries:
                raise
            wait = 2 ** (attempt - 1)
            print(f"Download failed ({e}); retry {attempt}/{retries} in {wait}s...")
            time.sleep(wait)

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
        return [str(libdir / obj_name)]
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
    elif is_android:
        extra_link_args = [
            "-Wl,--whole-archive",
            static_libs[0],
            "-Wl,--no-whole-archive",
            "-lc++",
        ]
    elif system == "Linux":
        extra_link_args = [
            "-Wl,--whole-archive",
            static_libs[0],
            "-Wl,--no-whole-archive",
        ]

libraries = get_curl_libraries()

ffibuilder.set_source(
    "curl_cffi._wrapper",
    """
        #include "shim.h"
    """,
    library_dirs=[str(libdir)],
    runtime_library_dirs=(
        [str(libdir)] if is_dynamic and arch["system"] != "Windows" else []
    ),
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
