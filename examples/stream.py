from curl_cffi import requests


with requests.Session() as s:
    r = s.get("https://httpbin.org/stream/20", stream=True)
    for chunk in r.iter_content():
        print("CHUNK", chunk)


with requests.Session() as s:
    r = s.get("https://httpbin.org/stream/20", stream=True)
    for line in r.iter_lines():
        print("LINE", line.decode())
