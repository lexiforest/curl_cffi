import sys
from curl_constants import CurlOpt, CurlInfo
try:
	from ._curl_cffi import ffi, lib
except ImportError:
	ffi = lib = None


class Curl(object):
	def __init__(self):
		self.instance = lib.bind_curl_easy_init()
		self.buffer_values = {}

	def __del__(self):
		self.close()

	def setopt(self, option, value):
		original_value = value
		input_option = {
			0: "int*",
			10000: "char*",
			20000: "void*",
			30000: "int*",  # offset type
		}

		# Convert value
		value_type = input_option.get(int(option / 10000) * 10000)
		if value_type in ["int*"]:
			value = ffi.new(value_type, value)
		elif option in [CurlOpt.WRITEFUNCTION, CurlOpt.WRITEDATA]:
			print("write_data")
			value = lib.make_string()
			target_func = original_value
			if option == CurlOpt.WRITEDATA:
				target_func = original_value.write
			self.buffer_values[option] = (target_func, value)
			option = CurlOpt.WRITEDATA
		elif option in [CurlOpt.HEADERFUNCTION, CurlOpt.WRITEHEADER]:
			value = lib.make_string()
			target_func = original_value
			if option == CurlOpt.WRITEHEADER:
				target_func = original_value.write
			self.buffer_values[option] = (target_func, value)
			option = CurlOpt.WRITEHEADER
		elif value_type in ["char*"]:
			pass  # Pass string as is
		else:
			raise NotImplementedError("Option unsupported: %s" % option)
		print(option, value)
		print(CurlOpt.WRITEDATA)
		val = lib.bind_curl_easy_setopt(self.instance, option, value)
		assert val == 0
		return val

	def getinfo(self, option):
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
		ret_val = ffi.new(ret_option[option & 0xF00000])
		assert lib.bind_curl_easy_getinfo(self.instance, option, ret_val) == 0
		return ret_cast_option[option & 0xF00000](ret_val[0])

	def perform(self):
		lib.bind_curl_easy_perform(self.instance)
		# Invoke the callbacks
		for option in self.buffer_values:
			obj = self.buffer_values[option][1]
			self.buffer_values[option][0](ffi.buffer(obj.content, obj.size)[:])

	# Free memory allocated
	def close(self):
		if self.instance:
			lib.bind_curl_easy_cleanup(self.instance)
			self.instance = None

			opt_to_delete = []
			for option in self.buffer_values:
				opt_to_delete.append(self.buffer_values[option][1])
				self.buffer_values[option] = (self.buffer_values[option][0], ffi.gc(self.buffer_values[option][1], lib.free_string))
			self.buffer_values = {}


def patch_as_pycurl():
	from . import pycurl_patch  # Force package to be loaded so it appears in sys.modules
	sys.modules["curl"] = sys.modules["pycurl"] = sys.modules["python_curl_cffi.pycurl_patch"]
