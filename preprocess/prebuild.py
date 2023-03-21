from urllib.request import urlretrieve
import os
import platform
import sys
import shutil

uname = platform.uname()

VERSION="0.5.4"
CURL_VERSION="7.84.0"
if uname.system == "Windows":
    LIBDIR = "./lib"
elif uname.system == "Darwin" and uname.machine == "x86_64":
    LIBDIR = "/Users/runner/work/_temp/install/lib"
else:
    LIBDIR="/usr/local/lib"


def reporthook(blocknum, blocksize, totalsize):
    readsofar = blocknum * blocksize
    if totalsize > 0:
        percent = readsofar * 1e2 / totalsize
        s = "\r%5.1f%% %*d / %d" % (
            percent, len(str(totalsize)), readsofar, totalsize)
        sys.stderr.write(s)
        if readsofar >= totalsize: # near the end
            sys.stderr.write("\n")
    else: # total size is unknown
        sys.stderr.write("read %d\n" % (readsofar,))


print("Download firefox certs, see: https://curl.se/docs/caextract.html")
urlretrieve("https://curl.se/ca/cacert.pem", "curl_cffi/cacert.pem", reporthook)


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
if os.path.exists(filename):
    print("libcurl-impersonate already exists")
else:
    print(f"Download libcurl-impersonate-chrome from {url}")
    urlretrieve(url, filename, reporthook)
shutil.unpack_archive(filename, LIBDIR)


# TODO download curl automatically

