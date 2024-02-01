import os
import platform
import shutil
import struct
from distutils.command.build import build
from pathlib import Path
from urllib.request import urlretrieve

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel

__version__ = "0.6.0b9"


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        if python.startswith("cp"):
            # on CPython, our wheels are abi3 and compatible back to 3.8
            return "cp38", "abi3", plat

        return python, abi, plat


def abs_machine():
    machine = platform.machine()

    pointer_bits = struct.calcsize("P") * 8
    if pointer_bits not in (32, 64):
        raise Exception("Unsupported pointer size")

    is_64 = pointer_bits == 64

    # x86 based archs
    if machine in ('AMD64', 'x86_64', 'i686'):
        return "x86_64" if is_64 else "i686"
    # arm based archs
    elif machine in ('aarch64', 'arm64', 'armv6l', 'armv7l'):
        return "aarch64" if is_64 else "arm"
    else:
        raise Exception("Unsupported processor")


def download_so():
    system = platform.system()
    machine = abs_machine()

    if system == "Windows":
        sysname = "win32"
        so_name = "libcurl.dll"

        if machine == "x86_64":
            libdir = "./lib64"
        elif machine == "i686":
            libdir = "./lib32"
        else:
            so_name = "SKIP"

    elif system == "Darwin":
        sysname = "macos"
        so_name = "libcurl-impersonate-chrome.4.dylib"

        if machine in ("x86_64", "aarch64"):
            libdir = "/Users/runner/work/_temp/install/lib"
            # FIXME from `curl-impersonate`
            if machine == "aarch64":
                machine = "arm64"
        else:
            so_name = "SKIP"

    else:
        sysname = "linux-gnu"
        so_name = "libcurl-impersonate-chrome.so"

        if machine in ("x86_64", "arm", "aarch64"):
            libdir = os.path.expanduser("~/.local/lib")
        else:
            so_name = "SKIP"

    if so_name == "SKIP":
        print(f"libcurl for {sysname} platform is not available on github.")
        return

    if (Path(libdir) / so_name).exists():
        print(".so files alreay downloaded.")
        return

    file = "libcurl-impersonate.tar.gz"
    url = (
        f"https://github.com/yifeikong/curl-impersonate/releases/download/"
        f"v{__version__}/libcurl-impersonate-v{__version__}"
        f".{machine}-{sysname}.tar.gz"
    )

    print(f"Downloading libcurl-impersonate-chrome from {url}...")
    urlretrieve(url, file)

    print("Unpacking downloaded files...")
    os.makedirs(libdir, exist_ok=True)
    shutil.unpack_archive(file, libdir)

    if system == "Windows":
        shutil.copy2(f"{libdir}/libcurl.dll", "curl_cffi")


class my_build(build):
    def run(self):
        download_so()
        super().run()


setup(
    # this option is only valid in setup.py
    cffi_modules=["scripts/build.py:ffibuilder"],
    cmdclass={
        "bdist_wheel": bdist_wheel_abi3,  # type: ignore
        "build": my_build,  # type: ignore
    },
)
