---
name: Bug report
about: Report a bug in curl_cffi
title: ""
labels: bug

---

<!--
If you want to ask for why a certain site blocks you, please ask in the discussion section.

Issues are for bug reports and feature requests, documentation improvements, not how to use curl_cffi.
-->

Please check the following items and answer all the questions when reporting a bug, 
otherwise it will be closed immediately.

- [ ] I'm not asking you to help bypass a specific site with ``curl_cffi``.
- [ ] A code snippet that can reproduce this bug will be provided, even if it's a one-liner.
- [ ] Version and environment information will be pasted as below.
- [ ] A `curl-cffi doctor` output will be included.

**Describe the bug**
A clear and concise description of what the bug is.

**To Reproduce**
```py
# Minimal reproducible code, like target websites, and request parameters, etc.
```

**Expected behavior**
A clear and concise description of what you expected to happen.

**Versions**
 - OS: [e.g. linux x64, Windows 7, macOS Sequoia]
 - curl_cffi version [e.g. 0.5.7, 0.7.3]
 - `pip freeze` dump

**`curl-cffi doctor` output**
```text
paste output here
```

**Additional context**
- Which session are you using? async or sync?
- If using async session, which loop implementation are you using?
- If you have tried, does this work with other http clients, e.g. `requests`, `httpx` or real browsers.
