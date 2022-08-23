import unittest
from io import BytesIO

from curl import Curl, CurlInfo, CurlOpt


class TestCurl(unittest.TestCase):
    def test_curl(self):
        b = BytesIO()
        c = Curl()
        c.setopt(CurlOpt.URL, "https://www.onfry.com")
        c.setopt(CurlOpt.WRITEDATA, b)
        c.perform()
        c.close()

        body = b.getvalue()
        print(body)
