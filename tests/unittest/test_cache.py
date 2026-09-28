from datetime import timedelta
import json
from pathlib import Path

import pytest

from curl_cffi.requests import cache
from curl_cffi.requests import AsyncSession, FileCacheBackend, Session
from curl_cffi.requests.models import Response


class CachedResponse(Response):
    @property
    def status(self):
        return self.status_code


def test_cache_hit_returns_cached_response(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/unique_cookie"))

    with Session(cache=cache) as session:
        first = session.get(url)
        second = session.get(url)

    assert first.cookies["foo"] == second.cookies["foo"]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_hit_updates_session_cookies(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/set_cookies"))

    with Session(cache=cache) as session:
        session.get(url)

    with Session(cache=cache) as session:
        response = session.get(url)

        assert response.cookies["foo"] == "bar"
        assert session.cookies["foo"] == "bar"


def test_cache_ignores_selected_query_params(server, tmp_path):
    cache = FileCacheBackend(
        expires=timedelta(seconds=60),
        path=tmp_path,
        ignored=["utm_source"],
    )
    first_url = str(
        server.url.copy_with(path="/unique_cookie", query=b"item=1&utm_source=a")
    )
    second_url = str(
        server.url.copy_with(path="/unique_cookie", query=b"item=1&utm_source=b")
    )

    with Session(cache=cache) as session:
        first = session.get(first_url)
        second = session.get(second_url)

    assert first.cookies["foo"] == second.cookies["foo"]
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_only_stores_successful_responses(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/retry_once", query=b"key=cache-test"))

    with Session(cache=cache) as session:
        first = session.get(url)
        second = session.get(url)
        third = session.get(url)

    assert first.status_code == 500
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_cache_uses_har_file_format(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/unique_cookie"))

    with Session(cache=cache) as session:
        session.get(url)

    cache_files = list(tmp_path.glob("*.json"))
    assert len(cache_files) == 1

    payload = json.loads(cache_files[0].read_text())
    entry = payload["log"]["entries"][0]
    assert payload["log"]["version"] == "1.2"
    assert entry["request"]["url"] == url
    assert entry["response"]["status"] == 200
    assert entry["response"]["content"]["encoding"] == "base64"
    assert entry["response"]["_curl_cffi"]["url"] == url


def test_cache_clear_removes_cache_files_only(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/unique_cookie"))
    extra_file = tmp_path / "keep.txt"
    extra_file.write_text("keep")

    with Session(cache=cache) as session:
        session.get(url)

    assert len(list(tmp_path.glob("*.json"))) == 1

    cache.clear()

    assert list(tmp_path.glob("*.json")) == []
    assert extra_file.read_text() == "keep"


def test_default_cache_path_is_private_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(cache.tempfile, "gettempdir", lambda: str(tmp_path))
    backend = FileCacheBackend(expires=timedelta(seconds=60))
    outside_file = tmp_path / f"{'a' * 64}.json"
    inside_file = backend.path / f"{'b' * 64}.json"
    outside_file.write_text("outside")
    inside_file.write_text("inside")

    backend.clear()

    assert backend.path == Path(tmp_path) / "curl_cffi_cache"
    assert outside_file.read_text() == "outside"
    assert not inside_file.exists()


def test_cache_preserves_custom_response_class(server, tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)
    url = str(server.url.copy_with(path="/unique_cookie"))

    with Session(cache=cache, response_class=CachedResponse) as session:
        session.get(url)
        cached = session.get(url)

    assert isinstance(cached, CachedResponse)
    assert cached.status == 200


def test_async_session_rejects_cache_backend():
    cache = FileCacheBackend(expires=timedelta(seconds=60))

    with pytest.raises(NotImplementedError, match="does not support cache yet"):
        AsyncSession(cache=cache)


def test_async_session_rejects_cache_shorthand():
    with pytest.raises(NotImplementedError, match="does not support cache yet"):
        AsyncSession(cache=timedelta(seconds=60))


def test_session_accepts_int_cache_shorthand():
    session = Session(cache=60)
    try:
        assert isinstance(session._cache, FileCacheBackend)
        assert session._cache.expires == timedelta(seconds=60)
    finally:
        session.close()


def test_session_accepts_timedelta_cache_shorthand():
    session = Session(cache=timedelta(minutes=2))
    try:
        assert isinstance(session._cache, FileCacheBackend)
        assert session._cache.expires == timedelta(minutes=2)
    finally:
        session.close()


def test_session_does_not_expose_cache_attribute():
    with Session() as session:
        assert not hasattr(session, "cache")


def test_cache_backend_property(tmp_path):
    cache = FileCacheBackend(expires=timedelta(seconds=60), path=tmp_path)

    with Session(cache=cache) as session:
        assert session.cache_backend is cache

    with Session() as session:
        assert session.cache_backend is None
