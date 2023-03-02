__all__ = ["Curl", "CurlInfo", "CurlOpt", "CurlError"]

import re
import os
from http.cookies import SimpleCookie
from typing import Any, List, Union, Optional

from ._const import CurlInfo, CurlOpt
from ._wrapper import ffi, lib


DEFAULT_CACERT = os.path.join(os.path.dirname(__file__), "cacert.pem")


class CurlError(Exception):
    pass


class Curl:
    def __init__(self, cacert: Optional[str] = None):
        self._curl = lib.curl_easy_init()
        self._write_callbacks = []
        self._headers = ffi.NULL
        self._cacert = cacert

    def __del__(self):
        self.close()

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
        elif option in (
            CurlOpt.WRITEFUNCTION,
            CurlOpt.WRITEDATA,
            CurlOpt.HEADERFUNCTION,
            CurlOpt.HEADERDATA,
        ):
            # WRITE/HEADERFUNCTION is void* and WRITEDATA/HEADER is char*
            if option in (CurlOpt.WRITEDATA, CurlOpt.HEADERDATA):
                target_func = value.write  # value is a buffer, use buffer.write
            else:
                target_func = value  # value is a callback
            c_value = lib.make_string()
            self._write_callbacks.append((target_func, c_value))
            if option == CurlOpt.WRITEFUNCTION:
                option = CurlOpt.WRITEDATA
            elif option == CurlOpt.HEADERFUNCTION:
                option = CurlOpt.HEADERDATA
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
        if ret != 0:
            raise CurlError(f"Failed to set option: {option} to: {value}, Error: {ret}")

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
        if ret != 0:
            raise CurlError(f"Failed to get info: {option}, Error: {ret}")
        if c_value[0] == ffi.NULL:
            return b""
        return ret_cast_option[option & 0xF00000](c_value[0])

    def version(self) -> bytes:
        return ffi.string(lib.curl_version())

    def impersonate(self, target: str, default_headers: bool = True) -> int:
        return lib.curl_easy_impersonate(
            self._curl, target.encode(), int(default_headers)
        )

    def perform(self):
        if self._cacert is None:
            self.setopt(CurlOpt.CAINFO, DEFAULT_CACERT)
        # TODO: use CURL_ERROR_SIZE
        error_buffer = ffi.new("char[]", 256)
        ret = lib._curl_easy_setopt(self._curl, CurlOpt.ERRORBUFFER, error_buffer)
        if ret != 0:
            raise CurlError(f"Failed to set error buffer")
        ret = lib.curl_easy_perform(self._curl)
        if ret != 0:
            raise CurlError(
                f"Failed to perform, ErrCode: {ret}, Reason: '{ffi.string(error_buffer).decode()}'"
            )
        # Invoke the write callbacks
        for func, binary_string in self._write_callbacks:
            func(ffi.buffer(binary_string.content, binary_string.size)[:])
        if self._headers != ffi.NULL:
            ret = lib.curl_slist_free_all(self._headers)
        self._headers = ffi.NULL

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

        for _, buffer in self._write_callbacks:
            ffi.gc(buffer, lib.free_string)
        self._write_callbacks = []
