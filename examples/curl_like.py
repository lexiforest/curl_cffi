from io import BytesIO

from curl_cffi import Curl, CurlOpt

buffer = BytesIO()
c = Curl()
c.setopt(CurlOpt.CUSTOMREQUEST, b"GET")
c.setopt(CurlOpt.URL, b"https://tls.browserleaks.com/json")
c.setopt(CurlOpt.WRITEDATA, buffer)
c.perform()
body = buffer.getvalue()
print("NO impersonate:")
print(body.decode())
print("")


buffer = BytesIO()
c.setopt(CurlOpt.WRITEDATA, buffer)
c.setopt(CurlOpt.URL, b"https://tls.browserleaks.com/json")
c.impersonate("chrome110")
c.setopt(CurlOpt.HTTPHEADER, [b"User-Agent: Curl/impersonate"])
c.perform()
body = buffer.getvalue()
print("with impersonate:")
print(body.decode())
c.close()
