from curl_cffi import Curl, CurlOpt, CurlInfo
from io import BytesIO

def main():
    buffer = BytesIO()
    c = Curl()
    c.setopt(CurlOpt.CUSTOMREQUEST, b"GET")
    c.setopt(CurlOpt.HTTP_VERSION, 1)
    c.setopt(CurlOpt.URL, b'https://ja3er.com/json')
    c.setopt(CurlOpt.URL, b'https://httpbin.org/ip')
    c.setopt(CurlOpt.USERAGENT, b'Mozilla/5.0')
    c.setopt(CurlOpt.VERBOSE, 1)
    c.setopt(CurlOpt.WRITEDATA, buffer)
    c.perform()
    c.close()
    body = buffer.getvalue()
    print(body.decode())

main()
