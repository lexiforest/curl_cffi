Pro (impersonate.pro)
=====================

These subcommands manage fingerprints and API access for
`impersonate.pro <https://impersonate.pro>`_.

Configure API key
-----------------

Store your impersonate.pro API key:

.. code-block:: bash

    curl-cffi config --api-key imp_xxxxxxxx

Update and list fingerprints
----------------------------

Download the latest fingerprints:

.. code-block:: bash

    curl-cffi update

List native + cached fingerprints in a table:

.. code-block:: bash

    curl-cffi list

Output fingerprints as JSON:

.. code-block:: bash

    curl-cffi list --json

Environment variables
---------------------

- ``IMPERSONATE_API_ROOT``: override API endpoint used by ``update``.
- ``IMPERSONATE_CONFIG_DIR``: override local config/cache directory.
