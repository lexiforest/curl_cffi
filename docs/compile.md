# How to compile

This page documents how to compile curl-impersonate and curl-cffi from source. If binary
package is not available on your platform, you may refer to this page for some inspirations.

!!! note

    This build process is very hacky now, but it works for most common systems.

    When people installing other python curl bindings, like `pycurl`, they often face
    compiling issues or OpenSSL issues, so I really hope that this package can be
    distributed as a compiled binary package, users would be able to use it by simply
    `pip install`, no more compile errors or `libcurl` mismatch whatsoever!

    For now, a pre-compiled `libcurl-impersonate` is downloaded from github and built
    into a bdist wheel, which is a binary package format used by PyPI. However, the
    right way is to download curl and curl-impersonate sources on our side and compile
    them all together.

    Help wanted!
