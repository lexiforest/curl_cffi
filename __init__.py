__all__ = ["Curl", "CurlInfo", "CurlOpt", "CurlError"]

from typing import Any, Union

from ._const import CurlInfo, CurlOpt

from . import _curl_cffi


class CurlError(Exception):
    pass


class Curl:
    def __init__(self):
        self._instance = _curl_cffi.lib.bind_curl_easy_init()
        self._write_callbacks = []

    def __del__(self):
        self.close()

    def setopt(self, option: CurlOpt, value: Any) -> int:
        input_option = {
            # this should be int in curl, but cffi requires pointer for void*
            # it will be convert back in the glue c code.
            0: "int*",
            10000: "char*",
            20000: "void*",
            30000: "int*",  # offset type
        }

        # Convert value
        value_type = input_option.get(int(option / 10000) * 10000)
        if value_type == "int*":
            c_value = _curl_cffi.ffi.new("int*", value)
        elif option in (
            CurlOpt.WRITEFUNCTION,
            CurlOpt.WRITEDATA,
            CurlOpt.HEADERFUNCTION,
            CurlOpt.WRITEHEADER,
        ):
            # WRITE/HEADERFUNCTION is void* and WRITEDATA/HEADER is char*
            if option in (CurlOpt.WRITEDATA, CurlOpt.WRITEHEADER):
                target_func = value.write  # value is a buffer, use buffer.write
            else:
                target_func = value  # value is a callback
            c_value = _curl_cffi.lib.make_string()
            self._write_callbacks.append((target_func, c_value))
            if option == CurlOpt.WRITEFUNCTION:
                option = CurlOpt.WRITEDATA
            if option == CurlOpt.HEADERFUNCTION:
                option = CurlOpt.WRITEHEADER
        elif value_type in ["char*"]:
            c_value = value
        else:
            raise NotImplementedError("Option unsupported: %s" % option)
        ret = _curl_cffi.lib.bind_curl_easy_setopt(self._instance, option, c_value)
        if ret != 0:
            raise CurlError(f"Failed to set option: {option} to: {value}, Error: {ret}")
        return ret

    def getinfo(self, option: CurlInfo) -> Union[str, int, float]:
        ret_option = {
            0x100000: "char*",
            0x200000: "long*",
            0x300000: "double*",
        }
        ret_cast_option = {
            0x100000: str,
            0x200000: int,
            0x300000: float,
        }
        c_value = _curl_cffi.ffi.new(ret_option[option & 0xF00000])
        ret = _curl_cffi.lib.bind_curl_easy_getinfo(self._instance, option, c_value)
        if ret != 0:
            raise CurlError(f"Failed to get info: {option}, Error: {ret}")
        return ret_cast_option[option & 0xF00000](c_value[0])

    def version(self) -> bytes:
        return _curl_cffi.ffi.string(_curl_cffi.lib.bind_curl_version())

    def perform(self) -> int:
        ret = _curl_cffi.lib.bind_curl_easy_perform(self._instance)
        # Invoke the write callbacks
        for func, binary_string in self._write_callbacks:
            func(_curl_cffi.ffi.buffer(binary_string.content, binary_string.size)[:])
        return ret

    def close(self):
        if self._instance:
            _curl_cffi.lib.bind_curl_easy_cleanup(self._instance)
            self._instance = None

        for _, buffer in self._write_callbacks:
            _curl_cffi.ffi.gc(buffer, _curl_cffi.lib.free_string),
        self._write_callbacks = []
