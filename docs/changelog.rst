Change Log
==========

v0.7
----

- v0.7.0
    - Added more recent impersonate versions, up to Chrome 124
    - Upgraded libcurl to 8.5.0

v0.6
----

The minimum Python version is now 3.8.

- v0.6.1
    - ``AsyncSession.close`` is now a coroutine.
    - This is a bugfix release.

- v0.6.0
    - Added more recent impersonate versions, up to Chrome 120 and Safari 17.0
    - Upgraded libcurl to 8.1.1
    - Added experimental websocket support
    - Supported proactive eventloop on Windows
    - Added win32 and macOS arm64 build targets
    - Added `allow_redirects` to Session parameters
    - Use certifi to replace packaged cacert.pem
    - Improved proxy support by accepting `proxy=...`
    - Bumped minimum python versiont to 3.8
    - Added files support
    - Added client certs support
    - Incorporated build time files for sdist
    - Bugfix: async curl timer leak

v0.5
----

- v0.5.10
    - Add stream support
    - Add support for secure cookies
    - Add curl_infos to extract extra info after performing
    - Bugfix: `timeout=None` not working
- v0.5.9
    - Add interface support
    - Make POST work as in real world
    - Add support for custom resolve
    - Switched to libcurl's COOKIELIST to sync cookies between python and curl
    - Add default_headers option for sessions like in curl-impersonate
    - Add curl_options for extra curl_options in Session
    - Add http_version option for limiting http version to 1.1 or whatever
    - Add debug option for extra curl debug info
    - Add CurlError.code
    - Bugfix: duplicated header lines for the same header
    - Bugfix: clearing headers when request fails
    - Bugfix: fix HEAD request
    - Bugfix: reset curl options when errors occur
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

v0.4
----

- 0.4.0
    - Removed c shim callback function, use cffi native callback function

v0.3
----

- 0.3.6
    - Updated to curl-impersonate v0.5.4, supported chrome107 and chrome110
- 0.3.0, copied more code from `httpx` to support session
    - Add `requests.Session`
    - Breaking change: `Response.cookies` changed from `http.cookies.SimpleCookie` to `curl_cffi.requests.Cookies`
    - Using ABI3 wheels to reduce package size.

