import os
import platform
import shutil
import struct
from pathlib import Path
from setuptools import setup
from urllib.request import urlretrieve
from wheel.bdist_wheel import bdist_wheel
from distutils.command.build import build


__version__ = "0.6.0b9"


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        if python.startswith("cp"):
            # on CPython, our wheels are abi3 and compatible back to 3.8
            return "cp38", "abi3", plat

        return python, abi, plat


def download_so():
    uname = platform.uname()
    machine = uname.machine

    # do not download if target platfrom dll not found

    if uname.system == "Windows":
        sysname = "win32"
        if struct.calcsize("P") * 8 == 64:
            machine = "x86_64"
            libdir = "./lib64"
        else:
            machine = "i686"
            libdir = "./lib32"
        so_name = "libcurl.dll"
    elif uname.system == "Darwin":
        sysname = "macos"
        libdir = "/Users/runner/work/_temp/install/lib"
        so_name = "libcurl-impersonate-chrome.4.dylib"
    else:
        sysname = "linux-gnu"
        libdir = "/usr/local/lib"
        so_name = "libcurl-impersonate-chrome.so"

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
    if uname.system == "Windows":
        shutil.copy2(f"{libdir}/libcurl.dll", "curl_cffi")


class my_build(build):
    def run(self):
        download_so()
        super().run()


setup(
    # this option is only valid in setup.py
    cffi_modules=["curl_cffi/build.py:ffibuilder"],
    cmdclass={
        "bdist_wheel": bdist_wheel_abi3,  # type: ignore
        "build": my_build,  # type: ignore
    },
)
