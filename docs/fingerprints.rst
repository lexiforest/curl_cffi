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

    FingerprintManager.enable_pro("imp_xxxxxxxx")

Update fingerprints
===================

From CLI:

.. code-block:: sh

    curl-cffi update

From Python:

.. code-block:: python

    from curl_cffi.fingerprints import FingerprintManager

    FingerprintManager.update_fingerprints()

Load local fingerprints
=======================

.. code-block:: python

    from curl_cffi.fingerprints import FingerprintManager

    fingerprints = FingerprintManager.load_fingerprints()
    print(len(fingerprints))
    print(fingerprints["chrome136"])

Storage paths
=============

By default, local files are written under ``~/.config/impersonate``:

- ``config.json``: API key config
- ``profiles.json``: cached fingerprints

Override the directory with ``IMPERSONATE_CONFIG_DIR``.
