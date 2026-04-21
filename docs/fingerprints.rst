Fingerprint Updates
*******************

curl_cffi provides fingerprint updates for professional users via
`impersonate.pro <https://impersonate.pro>`_.

Feature matrix
==============

.. list-table:: Feature matrix
   :widths: 24 12 12 28
   :header-rows: 1

   * - Edition
     - HTTP/2
     - HTTP/3
     - Fingerprint updates
   * - Open source
     - ✅
     - ✅
     - Major releases
   * - Commercial update
     - ✅
     - ✅
     - Frequent updates

Configure access
================

Set your API key once:

.. code-block:: sh

    curl-cffi config --api-key imp_xxxxxxxx

or in Python:

.. code-block:: python

    from curl_cffi.fingerprints import FingerprintManager

    FingerprintManager.set_api_key("imp_xxxxxxxx")

Or override the configured key at runtime:

.. code-block:: sh

    export IMPERSONATE_API_KEY=imp_xxxxxxxx

Update fingerprints
===================

From CLI:

.. code-block:: sh

    curl-cffi update

From Python:

.. code-block:: python

    from curl_cffi.fingerprints import FingerprintManager

    updated = FingerprintManager.update_fingerprints()
    print(updated)

Load local fingerprints
=======================

.. code-block:: python

    from curl_cffi.fingerprints import FingerprintManager

    fingerprints = FingerprintManager.load_fingerprints()
    print(len(fingerprints))
    print(fingerprints["chrome136"])

Load and edit fingerprints
==========================

For fingerprint-backed targets, you can load a fresh editable ``Fingerprint`` object
and pass it back to a request with the ``impersonate=...`` parameter.

.. code-block:: python

    import curl_cffi

    fingerprint = curl_cffi.get_fingerprint("edge_146_macos_26")
    fingerprint.headers["User-Agent"] = "..."

    r = curl_cffi.get(
        "https://example.com",
        impersonate=fingerprint,
    )

Storage paths
=============

By default, local files are written to a platform-native config directory:

- Linux: ``$XDG_CONFIG_HOME/impersonate`` or ``~/.config/impersonate``
- macOS: ``~/.config/impersonate``
- Windows: ``%APPDATA%\impersonate``

Files stored there:

- ``config.json``: API key config
- ``fingerprints.json``: cached fingerprints

Environment overrides:

- ``IMPERSONATE_API_KEY``: override the API key loaded from ``config.json``.
- ``IMPERSONATE_CONFIG_DIR``: override the config/cache directory.
