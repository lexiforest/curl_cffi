import asyncio
import base64
import json
from contextlib import suppress

import pytest

from curl_cffi.requests import AsyncSession, RequestsError
from curl_cffi.requests.errors import SessionClosed


async def test_get(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url))
        assert r.status_code == 200


def test_create_session_out_of_async(server):
    s = AsyncSession()

    async def get():
        r = await s.get(str(server.url))
        assert r.status_code == 200

    asyncio.run(get())


async def test_post_dict(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b"foo=bar"


async def test_post_str(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}')
        assert r.status_code == 200
        assert r.content == b'{"foo": "bar"}'


async def test_post_json(server):
    async with AsyncSession() as s:
        r = await s.post(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b'{"foo":"bar"}'


async def test_put_json(server):
    async with AsyncSession() as s:
        r = await s.put(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b'{"foo":"bar"}'


async def test_delete(server):
    async with AsyncSession() as s:
        r = await s.delete(str(server.url.copy_with(path="/echo_body")))
        assert r.status_code == 200


async def test_options(server):
    async with AsyncSession() as s:
        r = await s.options(str(server.url.copy_with(path="/echo_body")))
        assert r.status_code == 200


async def test_base_url(server):
    async with AsyncSession(
        base_url=str(server.url.copy_with(path="/a/b", params={"foo": "bar"}))
    ) as s:
        # target path is empty
        r = await s.get("")
        assert r.url == s.base_url

        # target path only has params
        r = await s.get("", params={"hello": "world"})
        assert r.url == str(server.url.copy_with(path="/a/b", params={"hello": "world"}))

        # target path is a relative path without starting /
        r = await s.get("x")
        assert r.url == str(server.url.copy_with(path="/a/x"))
        r = await s.get("x", params={"hello": "world"})
        assert r.url == str(server.url.copy_with(path="/a/x", params={"hello": "world"}))

        # target path is a relative path with starting /
        r = await s.get("/x")
        assert r.url == str(server.url.copy_with(path="/x"))
        r = await s.get("/x", params={"hello": "world"})
        assert r.url == str(server.url.copy_with(path="/x", params={"hello": "world"}))

        # target path is an absolute url
        r = await s.get(str(server.url.copy_with(path="/x/y")))
        assert r.url == str(server.url.copy_with(path="/x/y"))


async def test_params(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


async def test_update_params(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/echo_params?foo=z")), params={"foo": "bar"})
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


async def test_headers(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/echo_headers")), headers={"foo": "bar"})
        headers = r.json()
        assert headers["Foo"][0] == "bar"


async def test_cookies(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")),
            cookies={"foo": "bar", "hello": "world"},
        )
        cookies = r.json()
        assert cookies["foo"] == "bar"


async def test_auth(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/echo_headers")), auth=("foo", "bar"))
        assert r.status_code == 200
        assert r.json()["Authorization"][0] == f"Basic {base64.b64encode(b'foo:bar').decode()}"


async def test_timeout(server):
    with pytest.raises(RequestsError):
        async with AsyncSession() as s:
            await s.get(str(server.url.copy_with(path="/slow_response")), timeout=0.1)


async def test_not_follow_redirects(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/redirect_301")), allow_redirects=False)
        assert r.status_code == 301
        assert r.redirect_count == 0
        assert r.content == b"Redirecting..."


async def test_follow_redirects(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/redirect_301")), allow_redirects=True)
        assert r.status_code == 200
        assert r.redirect_count == 1


async def test_verify(https_server):
    async with AsyncSession() as s:
        with pytest.raises(RequestsError, match="SSL certificate problem"):
            await s.get(str(https_server.url), verify=True)


async def test_verify_false(https_server):
    async with AsyncSession() as s:
        r = await s.get(str(https_server.url), verify=False)
        assert r.status_code == 200


async def test_referer(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")),
            referer="http://example.com",
        )
        headers = r.json()
        assert headers["Referer"][0] == "http://example.com"


#######################################################################################
# testing response
#######################################################################################


async def test_redirect_url(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/redirect_301")), allow_redirects=True)
        assert r.url == str(server.url.copy_with(path="/"))


async def test_response_headers(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/set_headers")))
        assert r.headers.get_list("x-test") == ["test", "test2"]


async def test_response_cookies(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/set_cookies")))
        print(r.cookies)
        assert r.cookies["foo"] == "bar"


async def test_elapsed(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/slow_response")))
        assert r.elapsed > 0.1


async def test_reason(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/redirect_301")), allow_redirects=False)
        assert r.reason == "Moved Permanently"
        r = await s.get(str(server.url.copy_with(path="/redirect_301")), allow_redirects=True)
        assert r.status_code == 200
        assert r.reason == "OK"


#######################################################################################
# testing session
#######################################################################################


async def test_session_update_parms(server):
    async with AsyncSession(params={"old": "day"}) as s:
        r = await s.get(str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"})
        assert r.content == b'{"params": {"old": ["day"], "foo": ["bar"]}}'


async def test_session_preset_cookies(server):
    async with AsyncSession(cookies={"foo": "bar"}) as s:
        # send requests with other cookies
        r = await s.get(str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"})
        cookies = r.json()
        # old cookies should be persisted
        assert cookies["foo"] == "bar"
        # new cookies should be added
        assert cookies["hello"] == "world"


async def test_session_cookies(server):
    async with AsyncSession() as s:
        # let the server set cookies
        r = await s.get(str(server.url.copy_with(path="/set_cookies")))
        assert s.cookies["foo"] == "bar"
        # send requests with other cookies
        r = await s.get(str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"})
        cookies = r.json()
        # old cookies should be persisted
        assert cookies["foo"] == "bar"
        # new cookies should be added
        assert cookies["hello"] == "world"


# https://github.com/lexiforest/curl_cffi/issues/16
async def test_session_with_headers(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url), headers={"Foo": "bar"})
        r = await s.get(str(server.url), headers={"Foo": "baz"})
        assert r.status_code == 200


async def test_session_too_many_headers(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "1"})
        r = await s.get(str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "2"})
        headers = r.json()
        assert len(headers["Foo"]) == 1
        assert headers["Foo"][0] == "2"


# https://github.com/lexiforest/curl_cffi/issues/222
async def test_closed_session_throws_error():
    async with AsyncSession() as s:
        pass

    with pytest.raises(SessionClosed):
        await s.get("https://example.com")

    with pytest.raises(SessionClosed):
        await s.post("https://example.com")

    with pytest.raises(SessionClosed):
        await s.put("https://example.com")

    with pytest.raises(SessionClosed):
        await s.delete("https://example.com")

    with pytest.raises(SessionClosed):
        await s.options("https://example.com")

    with pytest.raises(SessionClosed):
        await s.head("https://example.com")

    with pytest.raises(SessionClosed):
        await s.patch("https://example.com")

    with pytest.raises(SessionClosed):
        await s.ws_connect("wss://example.com")


# https://github.com/lexiforest/curl_cffi/issues/39
async def test_post_body_cleaned(server):
    async with AsyncSession() as s:
        # POST with body
        r = await s.post(str(server.url), json={"foo": "bar"})
        # GET request with echo_body
        r = await s.get(str(server.url.copy_with(path="/echo_body")))
        # ensure body is empty
        assert r.content == b""


async def test_timers_leak(server):
    async with AsyncSession() as sess:
        for _ in range(3):
            with suppress(Exception):
                await sess.get(str(server.url.copy_with(path="/slow_response")), timeout=0.1)
        await asyncio.sleep(0.2)
        assert len(sess.acurl._timers) == 0


#######################################################################################
# async parallel
#######################################################################################


async def test_parallel(server):
    async with AsyncSession() as s:
        rs = [
            s.get(str(server.url.copy_with(path="/echo_headers")), headers={"Foo": f"{i}"})
            for i in range(6)
        ]
        tasks = [asyncio.create_task(r) for r in rs]
        rs = await asyncio.gather(*tasks)
        for idx, r in enumerate(rs):
            assert r.status_code == 200
            assert r.json()["Foo"][0] == str(idx)


async def test_stream_iter_content(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            async for chunk in r.aiter_content():
                assert b"path" in chunk


async def test_stream_iter_content_break(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            idx = 0
            async for chunk in r.aiter_content():
                idx += 1
                assert b"path" in chunk
                if idx == 3:
                    break
            assert r.status_code == 200


async def test_stream_iter_lines(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            async for chunk in r.aiter_lines():
                data = json.loads(chunk)
                assert data["path"] == "/stream"


async def test_stream_status_code(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            assert r.status_code == 200


async def test_stream_empty_body(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/empty_body"))
        async with s.stream("GET", url) as r:
            assert r.status_code == 200


async def test_stream_atext(server):
    async with AsyncSession() as s:
        url = str(server.url.copy_with(path="/stream"))
        async with s.stream("GET", url, params={"n": "20"}) as r:
            text = await r.atext()
            chunks = text.split("\n")
            assert len(chunks) == 20
