import sys
import platform
import subprocess

CONST_FILE = "curl_cffi/const.py"
CURL_VERSION = sys.argv[1]

uname = platform.uname()


print("extract consts from curl.h")
with open(CONST_FILE, "w") as f:
    f.write("# This file is automatically generated, do not modify it directly.\n\n")
    f.write("from enum import IntEnum\n\n\n")
    f.write("class CurlOpt(IntEnum):\n")
    cmd = rf"""
        echo '#include "{CURL_VERSION}/include/curl/curl.h"' | gcc -E - | grep -i "CURLOPT_.\+ =" | sed "s/  CURLOPT_/    /g" | sed "s/,//g"
    """
    output = subprocess.check_output(cmd, shell=True)
    f.write(output.decode())
    f.write(
        """
    if locals().get("WRITEDATA"):
        FILE = locals().get("WRITEDATA")
    if locals().get("READDATA"):
        INFILE = locals().get("READDATA")
    if locals().get("HEADERDATA"):
        WRITEHEADER = locals().get("HEADERDATA")\n\n
"""
    )

    f.write("class CurlInfo(IntEnum):\n")
    cmd = rf"""
        echo '#include "{CURL_VERSION}/include/curl/curl.h"' | gcc -E - | grep -i "CURLINFO_.\+ =" | sed "s/  CURLINFO_/    /g" | sed "s/,//g"
    """
    output = subprocess.check_output(cmd, shell=True)
    f.write(output.decode())
    f.write(
        """
    if locals().get("RESPONSE_CODE"):
        HTTP_CODE = locals().get("RESPONSE_CODE")\n\n
"""
    )

    f.write("class CurlMOpt(IntEnum):\n")
    cmd = rf"""
        echo '#include "{CURL_VERSION}/include/curl/curl.h"' | gcc -E - | grep -i "CURLMOPT_.\+ =" | sed "s/  CURLMOPT_/    /g" | sed "s/,//g"
    """
    output = subprocess.check_output(cmd, shell=True)
    f.write(output.decode())
    f.write("\n\n")


    f.write("class CurlECode(IntEnum):\n")
    cmd = rf"""
        echo '#include "{CURL_VERSION}/include/curl/curl.h"' | gcc -E - | grep -i CURLE_ | sed "s/[, ][=0]*//g" | sed "s/CURLE_/    /g" | awk '{{print $0 " = " NR-1}}'
    """
    output = subprocess.check_output(cmd, shell=True)
    f.write(output.decode())
    f.write("\n\n")


    f.write("class CurlHttpVersion(IntEnum):\n")
    f.write("    NONE = 0\n")
    f.write("    V1_0 = 1  # please use HTTP 1.0 in the request */\n")
    f.write("    V1_1 = 2  # please use HTTP 1.1 in the request */\n")
    f.write("    V2_0 = 3  # please use HTTP 2 in the request */\n")
    f.write("    V2TLS = 4  # use version 2 for HTTPS, version 1.1 for HTTP */\n")
    f.write("    V2_PRIOR_KNOWLEDGE = 5  # please use HTTP 2 without HTTP/1.1 Upgrade */\n")
    f.write("    V3 = 30  # Makes use of explicit HTTP/3 without fallback.\n")
