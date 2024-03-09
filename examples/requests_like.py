from curl_cffi import requests

r = requests.get("https://tls.browserleaks.com/json")
print("No impersonation", r.json())


r = requests.get("https://tls.browserleaks.com/json", impersonate="chrome101")
print("With impersonation", r.json())


s = requests.Session(impersonate="chrome110")
r = s.get("https://tls.browserleaks.com/json")
print("With impersonation", r.json())
