import platform
import sys

import curl_cffi


def print_doctor() -> None:
    print("curl-cffi doctor")
    print("----------------")
    print(f"python: {sys.version.split()[0]}")
    print(f"executable: {sys.executable}")
    print(f"platform: {platform.platform()}")
    print(f"machine: {platform.machine()}")
    print(f"curl_cffi: {curl_cffi.__version__}")
    print(f"libcurl: {curl_cffi.__curl_version__}")
