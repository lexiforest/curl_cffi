from curl_cffi import requests

class CustomResponse(requests.Response):
    @property
    def status(self):
        return self.status_code
    
    def custom_method():
        return "this is a custom method"
    
session = requests.Session(response_class=CustomResponse)
response: CustomResponse = session.get("http://example.com")
print(response.status)
print(response.custom_method())
