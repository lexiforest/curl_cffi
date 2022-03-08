import unittest
from python_curl_cffi import Curl, CurlOpt, CurlInfo
from io import BytesIO


class TestCurl(unittest.TestCase):
	def test_curl(self):
		b = BytesIO()
		c = Curl()
		c.setopt(CurlOpt.URL, 'https://www.onfry.com')
		c.setopt(CurlOpt.WRITEDATA, b)
		c.perform()
		c.close()

		body = b.getvalue()
		print(body)
