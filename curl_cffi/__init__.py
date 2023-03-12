__all__ = ["Curl", "CurlInfo", "CurlOpt", "CurlError"]

import os
import re
import warnings
from http.cookies import SimpleCookie
from typing import Any, List, Union

from ._const import CurlInfo, CurlOpt
from ._wrapper import ffi, lib

DEFAULT_CACERT = os.path.join(os.path.dirname(__file__), "cacert.pem")


class CurlError(Exception):
    pass


@ffi.def_extern()
def write_callback(ptr, size, nmemb, userdata):
    # import pdb; pdb.set_trace()
    # assert size == 1
    buffer = ffi.from_handle(userdata)
    buffer.write(ffi.buffer(ptr, nmemb)[:])
    return nmemb * size


class Curl:
    def __init__(self, cacert: str = DEFAULT_CACERT):
        self._curl = lib.curl_easy_init()
        self._headers = ffi.NULL
        self._cacert = cacert
        self._is_cert_set = False
        self._write_handle = None
        self._header_handle = None
        # TODO: use CURL_ERROR_SIZE
        self._error_buffer = ffi.new("char[]", 256)
        ret = lib._curl_easy_setopt(self._curl, CurlOpt.ERRORBUFFER, self._error_buffer)
        if ret != 0:
            warnings.warn(f"Failed to set error buffer")

    def __del__(self):
        self.close()

    def _check_error(self, errcode: int, action: str):
        if errcode != 0:
            errmsg = ffi.string(self._error_buffer).decode()
            raise CurlError(
                f"Failed to {action}, ErrCode: {errcode}, Reason: '{errmsg}'"
            )

    def setopt(self, option: CurlOpt, value: Any):
        input_option = {
            # this should be int in curl, but cffi requires pointer for void*
            # it will be convert back in the glue c code.
            0: "int*",
            10000: "char*",
            20000: "void*",
            30000: "int*",  # offset type
        }
        # print("option", option, "value", value)

        # Convert value
        value_type = input_option.get(int(option / 10000) * 10000)
        if value_type == "int*":
            c_value = ffi.new("int*", value)
        elif option in (CurlOpt.WRITEFUNCTION, CurlOpt.HEADERFUNCTION):
            raise NotImplementedError(
                "CurlOpt.WRITEFUNCTION/HEADERFUNCTION is not supported, you should use "
                "CurlOpt.WRITEDATA/HEADERDATA with io.BytesIO or other file-like objects. "
                "For example, instead of passing `buffer.write`, pass `buffer` directly."
            )
        elif option == CurlOpt.WRITEDATA:
            c_value = ffi.new_handle(value)
            self._write_handle = c_value
            lib._curl_easy_setopt(self._curl, CurlOpt.WRITEFUNCTION, lib.write_callback)
        elif option == CurlOpt.HEADERDATA:
            c_value = ffi.new_handle(value)
            self._header_handle = c_value
            lib._curl_easy_setopt(self._curl, CurlOpt.HEADERFUNCTION, lib.write_callback)
        elif value_type == "char*":
            if isinstance(value, str):
                c_value = value.encode()
            else:
                c_value = value
        else:
            raise NotImplementedError("Option unsupported: %s" % option)

        if option == CurlOpt.HTTPHEADER:
            for header in value:
                self._headers = lib.curl_slist_append(self._headers, header)
            ret = lib._curl_easy_setopt(self._curl, option, self._headers)
        else:
            ret = lib._curl_easy_setopt(self._curl, option, c_value)
        self._check_error(ret, "setopt(%s, %s)" % (option, value))

        if option == CurlOpt.CAINFO:
            self._is_cert_set = True

        return ret

    def getinfo(self, option: CurlInfo) -> Union[bytes, int, float]:
        ret_option = {
            0x100000: "char**",
            0x200000: "long*",
            0x300000: "double*",
        }
        ret_cast_option = {
            0x100000: ffi.string,
            0x200000: int,
            0x300000: float,
        }
        c_value = ffi.new(ret_option[option & 0xF00000])
        ret = lib.curl_easy_getinfo(self._curl, option, c_value)
        self._check_error(ret, action="getinfo(%s)" % option)
        if c_value[0] == ffi.NULL:
            return b""
        return ret_cast_option[option & 0xF00000](c_value[0])

    def version(self) -> bytes:
        return ffi.string(lib.curl_version())

    def impersonate(self, target: str, default_headers: bool = True) -> int:
        return lib.curl_easy_impersonate(
            self._curl, target.encode(), int(default_headers)
        )

    def perform(self, clear_headers: bool = True):
        # make sure we set a cacert store
        if not self._is_cert_set:
            ret = self.setopt(CurlOpt.CAINFO, self._cacert)
            self._check_error(ret, action="set cacert")

        # here we go
        ret = lib.curl_easy_perform(self._curl)
        self._check_error(ret, action="perform")

        # cleaning
        self._write_handle = None
        self._header_handle = None
        if clear_headers:
            self.clear_headers()

    def clear_headers(self) -> int:
        ret = 0
        if self._headers != ffi.NULL:
            ret = lib.curl_slist_free_all(self._headers)
        self._headers = ffi.NULL
        return ret

    def parse_cookie_headers(self, headers: List[bytes]) -> SimpleCookie:
        cookie = SimpleCookie()
        for header in headers:
            if header.lower().startswith(b"set-cookie: "):
                cookie.load(header[12:].decode())  # len("set-cookie: ") == 12
        return cookie

    def get_reason_phrase(self, status_line: bytes) -> bytes:
        m = re.match(rb"HTTP/\d\.\d [0-9]{3} (.*)", status_line)
        return m.group(1) if m else b""

    def close(self):
        if self._curl:
            lib.curl_easy_cleanup(self._curl)
            self._curl = None
        ffi.release(self._error_buffer)
