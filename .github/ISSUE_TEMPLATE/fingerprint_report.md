---
name: Fingerprint report
about: Report a new fingerprint not supported by curl_cffi
title: "New Fingerprint: "
labels: ""
---

Please make sure you fill out all the sections below, otherwise it will not be checked.

**Fingerprint**

Wireshark or similar tools are preferred, if you can not use them in your case, use: https://tls.browserleaks.com/json

- ja3n(tls fingerprint):
- akamai(http2 fingerprint):
- other bits not covered by above:

**Platform**

If you are reporint fingerprints from an app, it's your responsibility to figure out
which http client the app is using.

- Software: (e.g. Chrome, okhttp...)
- Version: (e.g. 131)
- OS and version: (e.g. Android 14, Windows 11)

**Additional context**

Have you checked that there is no custom options or extensions that will alter the TLS hello packet or HTTP/2 settings frame?

Can the fingerprint be impersonated via `ja3=` and `akamai=` parameters?

Paste the stack trace if it's not working.
