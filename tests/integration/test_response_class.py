from curl_cffi import requests

def test_default_response():
    response = requests.get("http://example.com")
    assert type(response) == requests.Response
    print(response.status_code)

class CustomResponse(requests.Response):
    @property
    def status(self):
        return self.status_code
    
def test_custom_response():
    session = requests.Session(response_class=CustomResponse)
    response = session.get("http://example.com")
    assert isinstance(response, CustomResponse)
    assert hasattr(response, "status")
    print(response.status)

class WrongTypeResponse: pass

def test_wrong_type_custom_response():
    try:
        requests.Session(response_class=WrongTypeResponse)
        assert False, "session was created without raising issue for wrong response class type"
    except TypeError:
        print("Wrong response class type detected")
