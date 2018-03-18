import unittest
import python_curl_cffi
from python_curl_cffi.curl_constants import CurlOpt
from StringIO import StringIO


class TestCurl(unittest.TestCase):
	def test_curl(self):
		b = StringIO()
		c = python_curl_cffi.Curl()
		c.setopt(CurlOpt.URL, 'https://www.onfry.com')
		c.setopt(CurlOpt.WRITEDATA, b)
		c.perform()
		c.close()

		body = b.getvalue()
		print(body)
