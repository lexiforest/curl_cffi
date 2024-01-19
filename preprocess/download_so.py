import os
import platform
import shutil
import sys
from urllib.request import urlretrieve


SYSTEMS_MAP = {"Darwin": "macos", "Windows": "win32"}
VERSION = sys.argv[1]


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

if system == "Windows":
    libdir = "./lib"
elif system == "Darwin" and machine == "x86_64":
    libdir = "/Users/runner/work/_temp/install/lib"
else:
    libdir = "/usr/local/lib"

if len(sys.argv) == 3 and sys.argv[2] == "win32":  # i686 32-bit flag
    machine = "i686"
elif machine == "AMD64":  # normalize 64-bit arch
    machine = "x86_64"

url = (
    f"https://github.com/yifeikong/curl-impersonate/releases/download/"
    f"v{VERSION}/libcurl-impersonate-v{VERSION}"
    f".{machine}-{SYSTEMS_MAP.get(system, 'linux-gnu')}.tar.gz"
)

print(f"Download libcurl-impersonate-chrome from {url}")
urlretrieve(
    url,
    "curl-impersonate.tar.gz",
    None if os.getenv("GITHUB_ACTIONS") else reporthook,
)

shutil.unpack_archive("curl-impersonate.tar.gz", libdir)
if system == "Windows":
    shutil.copy2(f"{libdir}/libcurl.dll", "curl_cffi")
