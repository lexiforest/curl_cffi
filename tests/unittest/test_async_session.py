import asyncio
import base64

import pytest

from curl_cffi.requests import AsyncSession, RequestsError


async def test_get(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url))
        assert r.status_code == 200


async def test_post_dict(server):
    async with AsyncSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b"foo=bar"


async def test_post_str(server):
    async with AsyncSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}'
        )
        assert r.status_code == 200
        assert r.content == b'{"foo": "bar"}'


async def test_post_json(server):
    async with AsyncSession() as s:
        r = await s.post(
            str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"foo":"bar"}'


async def test_put_json(server):
    async with AsyncSession() as s:
        r = await s.put(
            str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"}
        )
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


async def test_params(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


async def test_update_params(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params?foo=z")), params={"foo": "bar"}
        )
        assert r.status_code == 200
        assert r.content == b'{"params": {"foo": ["bar"]}}'


async def test_headers(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"foo": "bar"}
        )
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
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), auth=("foo", "bar")
        )
        assert r.status_code == 200
        assert (
            r.json()["Authorization"][0]
            == f"Basic {base64.b64encode(b'foo:bar').decode()}"
        )


async def test_timeout(server):
    with pytest.raises(RequestsError):
        async with AsyncSession() as s:
            await s.get(str(server.url.copy_with(path="/slow_response")), timeout=0.1)


async def test_not_follow_redirects(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=False
        )
        assert r.status_code == 301
        assert r.redirect_count == 0
        assert r.content == b"Redirecting..."


async def test_follow_redirects(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
        )
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
        r = await s.get(
            str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
        )
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


async def test_session_update_parms(server):
    async with AsyncSession(params={"old": "day"}) as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
        )
        assert r.content == b'{"params": {"old": ["day"], "foo": ["bar"]}}'


async def test_session_preset_cookies(server):
    async with AsyncSession(cookies={"foo": "bar"}) as s:
        # send requests with other cookies
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
        )
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
        r = await s.get(
            str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
        )
        cookies = r.json()
        # old cookies should be persisted
        assert cookies["foo"] == "bar"
        # new cookies should be added
        assert cookies["hello"] == "world"


# https://github.com/yifeikong/curl_cffi/issues/16
async def test_session_with_headers(server):
    async with AsyncSession() as s:
        r = await s.get(str(server.url), headers={"Foo": "bar"})
        r = await s.get(str(server.url), headers={"Foo": "baz"})
        assert r.status_code == 200


async def test_session_too_many_headers(server):
    async with AsyncSession() as s:
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "1"}
        )
        r = await s.get(
            str(server.url.copy_with(path="/echo_headers")), headers={"Foo": "2"}
        )
        headers = r.json()
        assert len(headers["Foo"]) == 1
        assert headers["Foo"][0] == "2"


# https://github.com/yifeikong/curl_cffi/issues/39
async def test_post_body_cleaned(server):
    async with AsyncSession() as s:
        # POST with body
        r = await s.post(str(server.url), json={"foo": "bar"})
        # GET request with echo_body
        r = await s.get(str(server.url.copy_with(path="/echo_body")))
        # ensure body is empty
        assert r.content == b""


#######################################################################################
# async parallel
#######################################################################################


async def test_parallel(server):
    async with AsyncSession() as s:
        rs = [
            s.get(
                str(server.url.copy_with(path="/echo_headers")), headers={"Foo": f"{i}"}
            )
            for i in range(6)
        ]
        tasks = [asyncio.create_task(r) for r in rs]
        rs = await asyncio.gather(*tasks)
        for idx, r in enumerate(rs):
            assert r.status_code == 200
            assert r.json()["Foo"][0] == str(idx)
