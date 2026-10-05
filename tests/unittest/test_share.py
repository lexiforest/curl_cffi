import gc
import threading
from io import BytesIO
from unittest.mock import patch
from weakref import ref

import pytest

from curl_cffi import (
    Curl,
    CurlError,
    CurlInfo,
    CurlLockData,
    CurlOpt,
    CurlShare,
    CurlShareCode,
    Session,
    lib,
)


def test_curl_share_lifecycle():
    share = CurlShare()
    share.share(CurlLockData.COOKIE)
    share.unshare(CurlLockData.COOKIE)
    share.close()
    share.close()  # idempotent


def test_share_close_in_use_preserves_handle():
    share = CurlShare()
    session = Session(curl_share=share)
    duplicate = None
    try:
        with pytest.raises(CurlError) as exc:
            share.close()
        assert exc.value.code == CurlShareCode.IN_USE

        # A failed close must leave the share usable by streaming/ws duplicates.
        duplicate = session.curl.duphandle()
        session.close()
        with pytest.raises(CurlError) as exc:
            share.close()
        assert exc.value.code == CurlShareCode.IN_USE

        duplicate.close()
        share.close()
        share.close()
    finally:
        if duplicate is not None:
            duplicate.close()
        session.close()
        share.close()


def test_share_cleanup_in_session_cycle():
    gc.collect()
    cleanup_results = []

    class TracedLib:
        def __getattr__(self, name):
            return getattr(lib, name)

        def curl_share_cleanup(self, handle):
            result = lib.curl_share_cleanup(handle)
            cleanup_results.append(result)
            return result

    with patch("curl_cffi.curl.lib", TracedLib()):
        share = CurlShare()
        first = Session(curl_share=share, use_thread_local_curl=False)
        second = Session(curl_share=share, use_thread_local_curl=False)
        first.cycle = second
        second.cycle = first
        references = [ref(share), ref(first), ref(second)]
        del share, first, second
        gc.collect()

    assert all(reference() is None for reference in references)
    assert cleanup_results[-1] == CurlShareCode.OK
    assert cleanup_results.count(CurlShareCode.OK) == 1


def test_share_enables_cross_handle_connection_reuse(server):
    # connect sharing is only safe serialized: two handles, same thread.
    url = str(server.url)
    share = CurlShare(connect=True)

    def fetch(curl: Curl) -> int:
        curl.setopt(CurlOpt.URL, url.encode())
        curl.setopt(CurlOpt.SHARE, share._curl_share)
        curl.setopt(CurlOpt.WRITEDATA, BytesIO())
        curl.perform()
        num_connects = curl.getinfo(CurlInfo.NUM_CONNECTS)
        assert isinstance(num_connects, int)
        return num_connects

    first, second = Curl(), Curl()
    try:
        assert fetch(first) == 1  # opens a connection
        assert fetch(second) == 0  # reuses it from the shared cache
    finally:
        first.close()
        second.close()
        share.close()


def test_share_survives_reset(server):
    # The Session resets its handle after every request, so CURLOPT_SHARE must
    # survive curl_easy_reset; otherwise sharing would only work for the first
    # request on each handle.
    url = str(server.url)
    share = CurlShare(connect=True)

    def fetch(curl: Curl) -> int:
        curl.setopt(CurlOpt.URL, url.encode())
        curl.setopt(CurlOpt.WRITEDATA, BytesIO())
        curl.perform()
        num_connects = curl.getinfo(CurlInfo.NUM_CONNECTS)
        assert isinstance(num_connects, int)
        return num_connects

    first, second = Curl(), Curl()
    try:
        first.setopt(CurlOpt.SHARE, share._curl_share)
        assert fetch(first) == 1  # opens a connection
        second.setopt(CurlOpt.SHARE, share._curl_share)
        second.reset()  # clears options, but must keep the share attached
        assert fetch(second) == 0  # still reuses the shared connection
    finally:
        first.close()
        second.close()
        share.close()


def test_session_threaded_requests_with_share(server):
    url = str(server.url)
    results: list[int] = []
    errors: list[Exception] = []

    # default CurlShare shares only DNS + TLS sessions: safe across threads.
    with Session(curl_share=CurlShare()) as s:

        def worker() -> None:
            try:
                for _ in range(5):
                    results.append(s.get(url).status_code)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert not errors
    assert len(results) == 40
    assert all(code == 200 for code in results)


def test_share_reattached_to_streaming_handle(server):
    # A streamed request runs on a duphandle()'d handle, which does not inherit
    # CURLOPT_SHARE, so the session must re-attach the share to it.
    share = CurlShare()
    with Session(curl_share=share) as s:
        r = s.get(str(server.url), stream=True)
        try:
            assert r.curl is not None and r.curl._share is share
        finally:
            r.close()
