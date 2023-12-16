import platform
import shutil
from urllib.request import urlretrieve

uname = platform.uname()

VERSION = "0.5.4"

if uname.system == "Windows":
    LIBDIR = "./lib"
elif uname.system == "Darwin" and uname.machine == "x86_64":
    LIBDIR = "/Users/runner/work/_temp/install/lib"
else:
    LIBDIR = "/usr/local/lib"

if uname.system == "Darwin":
    if uname.machine == "arm64":
        # TODO Download my own build of libcurl-impersonate for M1 Mac
        url = ""
        filename = "./curl-impersonate.tar.gz"
    else:
        url = f"https://github.com/lwthiker/curl-impersonate/releases/download/v{VERSION}/libcurl-impersonate-v{VERSION}.{uname.machine}-macos.tar.gz"
        filename = "./curl-impersonate.tar.gz"
elif uname.system == "Windows":
    url = f"https://github.com/yifeikong/curl-impersonate-win/releases/download/v{VERSION}/curl-impersonate-chrome.tar.gz"
    filename = "./curl-impersonate.tar.gz"
else:
    url = f"https://github.com/lwthiker/curl-impersonate/releases/download/v{VERSION}/libcurl-impersonate-v{VERSION}.{uname.machine}-linux-gnu.tar.gz"
    filename = "./curl-impersonate.tar.gz"

if url:
    print(f"Download libcurl-impersonate-chrome from {url}")
    urlretrieve(url, filename)
    shutil.unpack_archive(filename, LIBDIR)
