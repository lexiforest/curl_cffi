import threading
from io import BytesIO

from curl_cffi import Curl, CurlInfo, CurlLockData, CurlOpt, CurlShare, Session


def test_curl_share_lifecycle():
    share = CurlShare()
    share.share(CurlLockData.COOKIE)
    share.unshare(CurlLockData.COOKIE)
    share.close()
    share.close()  # idempotent


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
