import json
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


def detect_arch():
    with open(Path(__file__).parent / "libs.json") as f:
        archs = json.loads(f.read())
    uname = platform.uname()
    pointer_size = struct.calcsize("P") * 8
    for arch in archs:
        if (
            arch["system"] == uname.system
            and arch["machine"] == uname.machine
            and arch["pointer_size"] == pointer_size
        ):
            return arch
    raise Exception(f"Unsupported arch: {uname}")


def download_so():
    arch = detect_arch()

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
