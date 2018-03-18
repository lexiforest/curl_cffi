from .. import Curl
from .. import curl_constants

for key in dir(curl_constants.CurlInfo):
	if key[0] != "_":
		globals()[key] = getattr(curl_constants.CurlInfo, key)

for key in dir(curl_constants.CurlOpt):
	if key[0] != "_":
		globals()[key] = getattr(curl_constants.CurlOpt, key)
