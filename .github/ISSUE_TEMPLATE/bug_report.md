---
name: Bug report
about: Report a bug in curl_cffi
title: ""
labels: bug

---

Please check the following items before reporting a bug, otherwise it may be closed immediately.

- [ ] **This is NOT a site-related "bugs"**, e.g. some site blocks me when using curl_cffi,
    UNLESS it has been verified that the reason is missing pieces in the impersonation.
- [ ] A code snippet that can reproduce this bug is provided, even if it's a one-liner.
- [ ] Version information will be pasted as below.

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
```
# Minimal reproducible code, like target websites, and request parameters, etc.
```

**Expected behavior**
A clear and concise description of what you expected to happen.

**Versions**
 - OS: [e.g. linux x64, Windows 7, macOS Sequoia]
 - curl_cffi version [e.g. 0.5.7, 0.7.3]
 - `pip freeze` dump

**Additional context**
- Which session are you using? async or sync?
- If using async session, which loop implementation are you using?
- If you have tried, does this work with other http clients, e.g. `requests`, `httpx` or real browsers.
