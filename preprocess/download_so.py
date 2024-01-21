import os
import platform
import shutil
import sys
import struct
from urllib.request import urlretrieve


def reporthook(blocknum, blocksize, totalsize):
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize
        s = "\r%5.1f%% %*d / %d" % (percent, len(str(totalsize)), readsofar, totalsize)
        sys.stderr.write(s)
        if readsofar >= totalsize:  # near the end
            sys.stderr.write("\n")
    else:  # total size is unknown
        sys.stderr.write("read %d\n" % (readsofar,))


uname = platform.uname()
system = uname.system
machine = uname.machine

SYSTEMS_MAP = {"Darwin": "macos", "Windows": "win32"}
VERSION = sys.argv[1]

if system == "Windows":
    libdir = "./lib"
    machine = "x86_64" if struct.calcsize("P") * 8 == 64 else "i686"
elif system == "Darwin" and machine == "x86_64":
    libdir = "/Users/runner/work/_temp/install/lib"
else:
    libdir = "/usr/local/lib"

url = (
    f"https://github.com/yifeikong/curl-impersonate/releases/download/"
    f"v{VERSION}/libcurl-impersonate-v{VERSION}"
    f".{machine}-{SYSTEMS_MAP.get(system, 'linux-gnu')}.tar.gz"
)
file = "curl-impersonate.tar.gz"

print(f"Downloading libcurl-impersonate-chrome from {url}")
urlretrieve(url, file, None if os.getenv("GITHUB_ACTIONS") else reporthook)

print("Unpacking downloaded files")
shutil.unpack_archive(file, libdir)
if system == "Windows":
    shutil.copy2(f"{libdir}/libcurl.dll", "curl_cffi")
