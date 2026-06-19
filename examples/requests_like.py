import curl_cffi

r = curl_cffi.get("https://fp.impersonate.pro/api/auto")
print("No impersonation", r.json())


r = curl_cffi.get("https://fp.impersonate.pro/api/auto", impersonate="chrome101")
print("With impersonation", r.json())


s = curl_cffi.Session(impersonate="chrome110")
r = s.get("https://fp.impersonate.pro/api/auto")
print("With impersonation", r.json())
