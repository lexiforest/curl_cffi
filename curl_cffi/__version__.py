# New in version 3.8.
# from importlib import metadata
from .curl import Curl


__title__ = "curl_cffi"
# __description__ = metadata.metadata("curl_cffi")["Summary"]
# __version__ = metadata.version("curl_cffi")
__description__ = "libcurl ffi bindings for Python, with impersonation support"
__version__ = "0.5.10"
__curl_version__ = Curl().version().decode()
