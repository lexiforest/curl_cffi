Doctor
======

The ``doctor`` subcommand prints diagnostic information useful for debugging:

.. code-block:: bash

    curl-cffi doctor

Example output:

.. code-block:: text

    curl-cffi doctor
    ----------------
    python: 3.10.20
    executable: /usr/bin/python3
    platform: macOS-15.4-arm64-arm-64bit
    machine: arm64
    curl_cffi: 0.15.0b4
    libcurl: libcurl/8.15.0
    api_root: https://api.impersonate.pro/v1
    config_path: /Users/you/.config/impersonate/config.json
    config_present: True
    api_key_configured: True
    fingerprint_path: /Users/you/.config/impersonate/fingerprints.json
    fingerprint_present: True
    fingerprint_count: 42
