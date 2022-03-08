# Python Curl CFFI

CFFI bindings for libcurl.

# Example Usage

```python
from python_curl_cffi import Curl, CurlOpt, CurlInfo
from io import BytesIO

def main():
    buffer = BytesIO()
    c = Curl()
    c.setopt(CurlOpt.URL, b'https://ja3er.com/json')
    c.setopt(CurlOpt.WRITEDATA, buffer)
    c.perform()
    c.close()
    body = buffer.getvalue()
    print(body.decode())

main()
```

# API

Curl object:
* setopt(CurlOpt, value): Sets curl options as in `curl_easy_setopt`
* perform(): Performs curl request, as in `curl_easy_perform`
* getinfo(CurlInfo): Gets information in response after curl perform, as in `curl_easy_getinfo`
* close(): Closes and cleans up the curl object, as in `curl_easy_cleanup`

Enum values to be used with `setopt` and `getinfo` can be accessed from `CurlOpt` and `CurlInfo`.

# Installation

**Unix**

1. Install libcurl (e.g. `apt-get install libcurl4-openssl-dev`)
2. pip install git+https://multippt@bitbucket.org/multippt/python_curl_cffi.git

**Windows (Python 2 64-bit)**

Replace `x64` with `x86` for 32-bit versions of Python.

Compile libcurl:
1. Install Microsoft Visual C++ Compiler (MSVC 2008). https://www.microsoft.com/en-us/download/details.aspx?id=44266
2. `git clone https://github.com/curl/curl.git`
3. Open MSVC C++ Command Prompt (MSVC 2008). Subsequent commands to be executed in this command prompt. 
4. Build libcurl. `cd <path to curl repo>\winbuild\ && nmake /f Makefile.vc mode=static VC=9 MACHINE=x64`
5. Set `LIB` environment variable (e.g. `set LIB=<path to curl repo>\builds\libcurl-vc9-x64-release-static-ipv6-sspi-winssl\lib`)
6. Set `INCLUDE` environment variable (e.g. `set INCLUDE=<path to curl repo>\builds\libcurl-vc9-x64-release-static-ipv6-sspi-winssl\include`)
7. pip install git+https://multippt@bitbucket.org/multippt/python_curl_cffi.git

**Windows (Python 3 64-bit)**

Replace `x64` with `x86` for 32-bit versions of Python.

Compile libcurl:
1. Install Microsoft Visual C++ Compiler (MSVC 2017+). https://www.visualstudio.com
2. `git clone https://github.com/curl/curl.git`
3. Open MSVC C++ Command Prompt. Subsequent commands to be executed in this command prompt.
4. Build libcurl. `cd <path to curl repo>\winbuild\ && nmake /f Makefile.vc mode=static VC=14 MACHINE=x64`
5. Set `LIB` environment variable (e.g. `set LIB=<path to curl repo>\builds\libcurl-vc14-x64-release-static-ipv6-sspi-winssl\lib`)
6. Set `INCLUDE` environment variable (e.g. `set INCLUDE=<path to curl repo>\builds\libcurl-vc14-x64-release-static-ipv6-sspi-winssl\include`)
7. pip install git+https://multippt@bitbucket.org/multippt/python_curl_cffi.git
