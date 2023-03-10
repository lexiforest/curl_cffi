import base64

import pytest

from curl_cffi import requests


def test_get(server):
    r = requests.get(str(server.url))
    assert r.status_code == 200


def test_post_dict(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b"foo=bar"

def test_post_str(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}')
    assert r.status_code == 200
    assert r.content == b'{"foo": "bar"}'

def test_post_json(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b'{"foo": "bar"}'


def test_put_json(server):
    r = requests.put(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b'{"foo": "bar"}'


def test_delete(server):
    r = requests.delete(str(server.url.copy_with(path="/echo_body")))
    assert r.status_code == 200


def test_parms(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
    )
    assert r.content == b'{"params": {"foo": ["bar"]}}'


def test_update_parms(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_params?foo=z")), params={"foo": "bar"}
    )
    assert r.content == b'{"params": {"foo": ["bar"]}}'


def test_headers(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")), headers={"foo": "bar"}
    )
    headers = r.json()
    assert headers["Foo"] == "bar"


def test_cookies(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_cookies")),
        cookies={"foo": "bar", "hello": "world"},
    )
    cookies = r.json()
    assert cookies["foo"] == "bar"


def test_auth(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")), auth=("foo", "bar")
    )
    assert r.status_code == 200
    assert r.json()["Authorization"] == f"Basic {base64.b64encode(b'foo:bar').decode()}"


def test_timeout(server):
    with pytest.raises(requests.RequestsError):
        r = requests.get(str(server.url.copy_with(path="/slow_response")), timeout=0.1)


def test_not_follow_redirects(server):
    r = requests.get(
        str(server.url.copy_with(path="/redirect_301")), allow_redirects=False
    )
    assert r.status_code == 301
    assert r.redirect_count == 0
    assert r.content == b"Redirecting..."


def test_follow_redirects(server):
    r = requests.get(
        str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
    )
    assert r.status_code == 200
    assert r.redirect_count == 1


def test_verify(https_server):
    with pytest.raises(requests.RequestsError, match="SSL certificate problem"):
        r = requests.get(str(https_server.url), verify=True)


def test_verify_false(https_server):
    r = requests.get(str(https_server.url), verify=False)
    assert r.status_code == 200


def test_referer(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")), referer="http://example.com"
    )
    headers = r.json()
    assert headers["Referer"] == "http://example.com"


#######################################################################################
# testing response
#######################################################################################


def test_redirect_url(server):
    r = requests.get(
        str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
    )
    assert r.url == str(server.url.copy_with(path="/"))


def test_response_headers(server):
    r = requests.get(str(server.url.copy_with(path="/set_headers")))
    assert r.headers.get_list("x-test") == ["test", "test2"]


def test_response_cookies(server):
    r = requests.get(str(server.url.copy_with(path="/set_cookies")))
    print(r.cookies)
    assert r.cookies["foo"] == "bar"


def test_elapsed(server):
    r = requests.get(str(server.url.copy_with(path="/slow_response")))
    assert r.elapsed > 0.1


def test_reason(server):
    r = requests.get(
        str(server.url.copy_with(path="/redirect_301")), allow_redirects=False
    )
    assert r.reason == "Moved Permanently"
    r = requests.get(
        str(server.url.copy_with(path="/redirect_301")), allow_redirects=True
    )
    assert r.status_code == 200
    assert r.reason == "OK"


#######################################################################################
# testing session
#######################################################################################


def test_session_explicitly(server):
    s = requests.Session()
    r = s.get(str(server.url))
    assert r.status_code == 200


def test_session_update_parms(server):
    s = requests.Session(params={"old": "day"})
    r = s.get(str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"})
    assert r.content == b'{"params": {"old": ["day"], "foo": ["bar"]}}'


def test_session_preset_cookies(server):
    s = requests.Session(cookies={"foo": "bar"})
    # send requests with other cookies
    r = s.get(
        str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
    )
    cookies = r.json()
    # old cookies should be persisted
    assert cookies["foo"] == "bar"
    # new cookies should be added
    assert cookies["hello"] == "world"


def test_session_cookies(server):
    s = requests.Session()
    # let the server set cookies
    r = s.get(str(server.url.copy_with(path="/set_cookies")))
    assert s.cookies["foo"] == "bar"
    # send requests with other cookies
    r = s.get(
        str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
    )
    cookies = r.json()
    # old cookies should be persisted
    assert cookies["foo"] == "bar"
    # new cookies should be added
    assert cookies["hello"] == "world"


# https://github.com/yifeikong/curl_cffi/issues/16
def test_session_with_headers(server):
    s = requests.Session()
    r = s.get(str(server.url), headers={"Foo": "bar"})
    r = s.get(str(server.url), headers={"Foo": "baz"})
    assert r.status_code == 200
