from importlib import import_module

from curl_cffi import _wrapper

version_module = import_module("curl_cffi.__version__")


def test_resolve_curl_version_does_not_need_easy_handle(monkeypatch):
    class DummyFFI:
        @staticmethod
        def string(value):
            return value

    class DummyLib:
        @staticmethod
        def curl_version():
            return b"libcurl/fake"

        @staticmethod
        def curl_easy_init():
            raise AssertionError("curl_easy_init should not be called")

    monkeypatch.setattr(_wrapper, "ffi", DummyFFI())
    monkeypatch.setattr(_wrapper, "lib", DummyLib())

    assert version_module._resolve_curl_version() == "libcurl/fake"
