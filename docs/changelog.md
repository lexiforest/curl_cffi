# Change Log

- v0.5
    - v0.5.7
        - Refactor JSON serialization to mimic browser behavior (#66)
        - Add http options to Session classes (#72)
        - Add Windows eventloop warning
    - v0.5.6
        - Make Session.curl a thread-local variable (#50)
        - Add support for eventlet and gevent with threadpool
        - Bugfix: Only close future if it's not done or cancelled
    - 0.5.5
        - Bugfix: Fix high CPU usage (#46)
    - 0.5.4
        - Bugfix: Fix cert and error buffer when calling curl_easy_reset
    - 0.5.3
        - Bugfix: Reset curl after performing, fix #39
    - 0.5.2
        - Bugfix: Clear headers after async perform
    - 0.5.1
        - Bugfix: Clean up timerfunction when curl already closed
    - 0.5.0
        - Added asyncio support

- v0.4
    - 0.4.0
        - Removed c shim callback function, use cffi native callback function

- v0.3
    - 0.3.6
        - Updated to curl-impersonate v0.5.4, supported chrome107 and chrome110
    - 0.3.0, copied more code from `httpx` to support session
        - Add `requests.Session`
        - Breaking change: `Response.cookies` changed from `http.cookies.SimpleCookie` to `curl_cffi.requests.Cookies`
        - Using ABI3 wheels to reduce package size.

TODOs:

- [x] Write docs.
- [x] Binary package for macOS(Intel/AppleSilicon) and Windows.
- [ ] Support musllinux(alpine) bdist by building from source.
- [x] Exclude the curl headers from source, download them when building.
- [x] Update curl header files and constants via scripts.
- [x] Implement `requests.Session/httpx.Client`.
- [x] Create [ABI3 wheels](https://cibuildwheel.readthedocs.io/en/stable/faq/#abi3) to reduce package size and build time.
- [x] Set default headers as in curl-impersonate wrapper scripts.
- [ ] Support stream in asyncio mode
    <!--use loop.call_soon(q.put_nowait), wait for headers, then let user iter over content -->
