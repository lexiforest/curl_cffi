import curl_cffi

r = curl_cffi.get("https://tls.browserleaks.com/json")
print("No impersonation", r.json())


r = curl_cffi.get("https://tls.browserleaks.com/json", impersonate="chrome101")
print("With impersonation", r.json())


s = curl_cffi.Session(impersonate="chrome110")
r = s.get("https://tls.browserleaks.com/json")
print("With impersonation", r.json())
