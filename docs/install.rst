Install
=======

Via pip
------

The simplest way is to install from PyPI:

.. code-block::

    pip install curl_cffi --upgrade

We have sdist(source distribution) and bdist(binary distribution) on PyPI. This should
work on Linux, macOS and Windows out of the box.

If it does not work on you platform, you may need to compile and install `curl-impersonate`
first and set some environment variables like `LD_LIBRARY_PATH`.

Beta versions
------------

To install beta releases:

.. code-block::

    pip install curl_cffi --upgrade --pre

Note the ``--pre`` option here means pre-releases.


Latest
------

To install the latest unstable version from GitHub:

.. code-block::

    git clone https://github.com/yifeikong/curl_cffi/
    cd curl_cffi
    make preprocess
    pip install .
