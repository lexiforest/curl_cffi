from curl_cffi import Curl, CurlOpt, CurlInfo, requests
from io import BytesIO

def main():
    buffer = BytesIO()
    c = Curl()
    c.setopt(CurlOpt.CUSTOMREQUEST, b"GET")
    c.setopt(CurlOpt.URL, b'https://tls.browserleaks.com/json')
    c.setopt(CurlOpt.WRITEDATA, buffer)
    c.perform()
    body = buffer.getvalue()
    print("NO impersonate:")
    print(body.decode())
    print("")

    buffer = BytesIO()
    c.setopt(CurlOpt.WRITEDATA, buffer)
    c.setopt(CurlOpt.URL, b'https://httpbin.org/headers')
    c.impersonate("chrome99")
    c.setopt(CurlOpt.HTTPHEADER, [b"User-Agent: Curl/impersonate"])
    c.perform()
    body = buffer.getvalue()
    print("with impersonate:")
    print(body.decode())
    c.close()

def main_requests():
    r = requests.get("https://tls.browserleaks.com/json")
    print(r.json())
    r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101")
    print(r.json())

main()

