from curl_cffi import requests
from curl_cffi.curl import Curl, CurlInfo
from typing import cast

class CustomResponse(requests.Response):
    def __init__(self, curl: Curl | None = None, request: requests.Request | None = None):
        super().__init__(curl, request)
        self.local_port = cast(int, curl.getinfo(CurlInfo.LOCAL_PORT))
        self.connect_time = cast(float, curl.getinfo(CurlInfo.CONNECT_TIME))

    @property
    def status(self):
        return self.status_code
    
    def custom_method(self):
        return "this is a custom method"
    
session = requests.Session(response_class=CustomResponse)
response: CustomResponse = session.get("http://example.com")
print(f"{response.status=}")
print(response.custom_method())
print(f"{response.local_port=}")
print(f"{response.connect_time=}")