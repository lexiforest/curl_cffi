import base64
import json
from contextlib import suppress

import pytest
import trio

from curl_cffi import Headers, TrioSession
from curl_cffi.requests import RequestsError
from curl_cffi.requests.errors import SessionClosed


@pytest.mark.trio
async def test_get(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url))
        assert r.status_code == 200


def test_create_session_out_of_async(server):
    s = TrioSession()

    async def get():
        r = await s.get(str(server.url))
        assert r.status_code == 200

    trio.run(get)


@pytest.mark.trio
async def test_post_dict(server):
    async with TrioSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b"foo=bar"


@pytest.mark.trio
async def test_post_str(server):
    async with TrioSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}'
        )
        assert r.status_code == 200
        assert r.content == b'{"foo": "bar"}'


@pytest.mark.trio
async def test_post_json(server):
    async with TrioSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"foo":"bar"}'


@pytest.mark.trio
async def test_put_json(server):
    async with TrioSession() as s:
        r = await s.put(
            str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"foo":"bar"}'


@pytest.mark.trio
async def test_delete(server):
    async with TrioSession() as s:
        r = await s.delete(str(server.url.copy_with(path="/echo_body")))
        assert r.status_code == 200


@pytest.mark.trio
async def test_options(server):
    async with TrioSession() as s:
        r = await s.options(str(server.url.copy_with(path="/echo_body")))
        assert r.status_code == 200


@pytest.mark.trio
async def test_base_url(server):
    async with TrioSession(
        base_url=str(server.url.copy_with(path="/a/b", params={"foo": "bar"}))
    ) as s:
        # target path is empty
        r = await s.get("")
        assert r.url == s.base_url

        # target path only has params
        r = await s.get("", params={"hello": "world"})
        assert r.url == str(
            server.url.copy_with(path="/a/b", params={"hello": "world"})
        )

        # target path is a relative path without starting /
        r = await s.get("x")
        assert r.url == str(server.url.copy_with(path="/a/x"))
        r = await s.get("x", params={"hello": "world"})
        assert r.url == str(
            server.url.copy_with(path="/a/x", params={"hello": "world"})
        )

        # target path is a relative path with starting /
        r = await s.get("/x")
        assert r.url == str(server.url.copy_with(path="/x"))
        r = await s.get("/x", params={"hello": "world"})
        assert r.url == str(server.url.copy_with(path="/x", params={"hello": "world"}))

        # target path is an absolute url
        r = await s.get(str(server.url.copy_with(path="/x/y")))
        assert r.url == str(server.url.copy_with(path="/x/y"))


@pytest.mark.trio
async def test_params(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


@pytest.mark.trio
async def test_update_params(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params?foo=z")), params={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


@pytest.mark.trio
async def test_headers(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"foo": "bar"}
        )
        headers = r.json()
        assert headers["Foo"][0] == "bar"


@pytest.mark.trio
async def test_headers_encoding_is_preserved(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url), headers=Headers(encoding="utf-8"))
        assert r.status_code == 200
        assert r.request is not None
        assert r.request.headers.encoding == "utf-8"


@pytest.mark.trio
async def test_cookies(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")),
            cookies={"foo": "bar", "hello": "world"},
        )
        cookies = r.json()
        assert cookies["foo"] == "bar"


@pytest.mark.trio
async def test_auth(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), auth=("foo", "bar")
        )
        assert r.status_code == 200
        assert (
            r.json()["Authorization"][0]
            == f"Basic {base64.b64encode(b'foo:bar').decode()}"
        )


@pytest.mark.trio
async def test_timeout(server):
    async with TrioSession() as s:
        with trio.fail_after(2):
            with pytest.raises(RequestsError):
                await s.get(
                    str(server.url.copy_with(path="/slow_response")), timeout=0.1
                )


@pytest.mark.trio
async def test_not_follow_redirects(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=False
        )
        assert r.status_code == 301
        assert r.redirect_count == 0
        assert r.content == b"Redirecting..."


@pytest.mark.trio
async def test_follow_redirects(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
        )
        assert r.status_code == 200
        assert r.redirect_count == 1


@pytest.mark.trio
async def test_verify(https_server):
    async with TrioSession() as s:
        with pytest.raises(RequestsError, match="SSL certificate problem"):
            await s.get(str(https_server.url), verify=True)


@pytest.mark.trio
async def test_verify_false(https_server):
    async with TrioSession() as s:
        r = await s.get(str(https_server.url), verify=False)
        assert r.status_code == 200


@pytest.mark.trio
async def test_referer(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")),
            referer="http://example.com",
        )
        headers = r.json()
        assert headers["Referer"][0] == "http://example.com"


#######################################################################################
# testing response
#######################################################################################


@pytest.mark.trio
async def test_redirect_url(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
        )
        assert r.url == str(server.url.copy_with(path="/"))


@pytest.mark.trio
async def test_response_headers(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url.copy_with(path="/set_headers")))
        assert r.headers.get_list("x-test") == ["test", "test2"]


@pytest.mark.trio
async def test_response_cookies(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url.copy_with(path="/set_cookies")))
        print(r.cookies)
        assert r.cookies["foo"] == "bar"


@pytest.mark.trio
async def test_elapsed(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url.copy_with(path="/slow_response")))
        assert r.elapsed.total_seconds() > 0.1


@pytest.mark.trio
async def test_reason(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=False
        )
        assert r.reason == "Moved Permanently"
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
        )
        assert r.status_code == 200
        assert r.reason == "OK"


#######################################################################################
# testing session
#######################################################################################


@pytest.mark.trio
async def test_session_update_parms(server):
    async with TrioSession(params={"old": "day"}) as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
        )
        assert r.content == b'{"params": {"old": ["day"], "foo": ["bar"]}}'


@pytest.mark.trio
async def test_session_preset_cookies(server):
    async with TrioSession(cookies={"foo": "bar"}) as s:
        # send requests with other cookies
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
        )
        cookies = r.json()
        # old cookies should be persisted
        assert cookies["foo"] == "bar"
        # new cookies should be added
        assert cookies["hello"] == "world"


@pytest.mark.trio
async def test_session_cookies(server):
    async with TrioSession() as s:
        # let the server set cookies
        r = await s.get(str(server.url.copy_with(path="/set_cookies")))
        assert s.cookies["foo"] == "bar"
        # send requests with other cookies
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
        )
        cookies = r.json()
        # old cookies should be persisted
        assert cookies["foo"] == "bar"
        # new cookies should be added
        assert cookies["hello"] == "world"


# https://github.com/lexiforest/curl_cffi/issues/16
@pytest.mark.trio
async def test_session_with_headers(server):
    async with TrioSession() as s:
        r = await s.get(str(server.url), headers={"Foo": "bar"})
        r = await s.get(str(server.url), headers={"Foo": "baz"})
        assert r.status_code == 200


@pytest.mark.trio
async def test_session_too_many_headers(server):
    async with TrioSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "1"}
        )
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "2"}
        )
        headers = r.json()
        assert len(headers["Foo"]) == 1
        assert headers["Foo"][0] == "2"


# https://github.com/lexiforest/curl_cffi/issues/222
@pytest.mark.trio
async def test_closed_session_throws_error(server):
    async with TrioSession() as s:
        pass
    base_url = str(server.url)
    ws_url = str(server.url.copy_with(scheme="ws"))

    with pytest.raises(SessionClosed):
        await s.get(base_url)

    with pytest.raises(SessionClosed):
        await s.post(base_url)

    with pytest.raises(SessionClosed):
        await s.put(base_url)

    with pytest.raises(SessionClosed):
        await s.delete(base_url)

    with pytest.raises(SessionClosed):
        await s.options(base_url)

    with pytest.raises(SessionClosed):
        await s.head(base_url)

    with pytest.raises(SessionClosed):
        await s.patch(base_url)

    with pytest.raises(SessionClosed):
        await s.ws_connect(ws_url)


# https://github.com/lexiforest/curl_cffi/issues/39
@pytest.mark.trio
async def test_post_body_cleaned(server):
    async with TrioSession() as s:
        # POST with body
        r = await s.post(str(server.url), json={"foo": "bar"})
        # GET request with echo_body
        r = await s.get(str(server.url.copy_with(path="/echo_body")))
        # ensure body is empty
        assert r.content == b""


@pytest.mark.skip(reason="No longer needed")
@pytest.mark.trio
async def test_timers_leak(server):
    async with TrioSession() as sess:
        for _ in range(3):
            with suppress(Exception):
                await sess.get(
                    str(server.url.copy_with(path="/slow_response")), timeout=0.1
                )
        await trio.sleep(0.2)


#######################################################################################
# async parallel
#######################################################################################


@pytest.mark.trio
async def test_parallel(server):
    async with TrioSession() as s:
        results = [None] * 8

        async def worker(idx: int) -> None:
            r = await s.get(
                str(server.url.copy_with(path="/echo_headers")),
                headers={"Foo": f"{idx}"},
            )
            results[idx] = r

        async with trio.open_nursery() as nursery:
            for idx in range(8):
                nursery.start_soon(worker, idx)

        for idx, r in enumerate(results):
            assert r is not None
            assert r.status_code == 200
            assert r.json()["Foo"][0] == str(idx)


@pytest.mark.trio
async def test_high_parallel(server):
    async with TrioSession() as s:
        results = [None] * 10240

        async def worker(idx: int) -> None:
            r = await s.get(
                str(server.url.copy_with(path="/echo_headers")),
                headers={"Foo": f"{idx}"},
            )
            results[idx] = r

        async with trio.open_nursery() as nursery:
            for idx in range(10240):
                nursery.start_soon(worker, idx)

        for idx, r in enumerate(results):
            assert r is not None
            assert r.status_code == 200
            assert r.json()["Foo"][0] == str(idx)


@pytest.mark.trio
async def test_stream_iter_content(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            async for chunk in r.aiter_content():
                assert b"path" in chunk


@pytest.mark.trio
async def test_stream_iter_content_break(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            idx = 0
            async for chunk in r.aiter_content():
                idx += 1
                assert b"path" in chunk
                if idx == 3:
                    break
            assert r.status_code == 200


@pytest.mark.trio
async def test_stream_iter_lines(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            async for chunk in r.aiter_lines():
                data = json.loads(chunk)
                assert data["path"] == "/stream"


@pytest.mark.trio
async def test_stream_status_code(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            assert r.status_code == 200


@pytest.mark.trio
async def test_stream_empty_body(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/empty_body"))
        async with s.stream("GET", url) as r:
            assert r.status_code == 200


@pytest.mark.trio
async def test_stream_atext(server):
    async with TrioSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            text = await r.atext()
            chunks = text.split("\n")
            assert len(chunks) == 20


@pytest.mark.trio
async def test_async_session_auto_raise_for_status_enabled(server):
    """Test that TrioSession automatically raises HTTPError for error status codes
    when raise_for_status=True"""
    from curl_cffi.requests.exceptions import HTTPError

    async with TrioSession(raise_for_status=True) as s:
        try:
            await s.get(str(server.url.copy_with(path="/status/404")))
            raise AssertionError("Should have raised HTTPError for 404")
        except HTTPError as e:
            assert e.response.status_code == 404  # type: ignore


@pytest.mark.trio
async def test_async_session_auto_raise_for_status_disabled(server):
    """Test that TrioSession does NOT raise HTTPError when raise_for_status=False
    (default)"""
    async with TrioSession(raise_for_status=False) as s:
        r = await s.get(str(server.url.copy_with(path="/status/404")))
        assert r.status_code == 404
        # Should not raise an exception
