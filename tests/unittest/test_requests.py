import base64
from io import BytesIO

import pytest

from curl_cffi import requests


def test_head(server):
    r = requests.head(str(server.url))
    assert r.status_code == 200


def test_get(server):
    r = requests.get(str(server.url))
    assert r.status_code == 200


def test_post_dict(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), data={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b"foo=bar"


def test_callback(server):
    buffer = BytesIO()
    r = requests.post(
        str(server.url.copy_with(path="/echo_body")),
        data={"foo": "bar"},
        content_callback=buffer.write,
    )
    assert r.status_code == 200
    assert buffer.getvalue() == b"foo=bar"


def test_post_str(server):
    r = requests.post(
        str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}'
    )
    assert r.status_code == 200
    assert r.content == b'{"foo": "bar"}'


def test_post_no_body(server):
    r = requests.post(
        str(server.url.copy_with(path="/")),
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 200


def test_post_json(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b'{"foo":"bar"}'


def test_put_json(server):
    r = requests.put(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b'{"foo":"bar"}'


def test_delete(server):
    r = requests.delete(str(server.url.copy_with(path="/echo_body")))
    assert r.status_code == 200


def test_options(server):
    r = requests.options(str(server.url.copy_with(path="/echo_body")))
    assert r.status_code == 200


def test_parms(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_params")), params={"foo": "bar"}
    )
    assert r.content == b'{"params": {"foo": ["bar"]}}'


def test_update_params(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_params?foo=z")), params={"foo": "bar"}
    )
    assert r.content == b'{"params": {"foo": ["bar"]}}'


def test_headers(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")), headers={"foo": "bar"}
    )
    headers = r.json()
    assert headers["Foo"][0] == "bar"


def test_content_type_header_with_json(server):
    # FIXME: this actually does not work, because the test server uvicorn will merge
    # Content-Type headers, so it always works even if there is duplicate headers.
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")),
        json={"foo": "bar"},
        headers={"content-type": "application/json"},
    )
    headers = r.json()
    assert len(headers["Content-type"]) == 1
    assert headers["Content-type"][0] == "application/json"
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")),
        json={"foo": "bar"},
        headers={"content-type": "application/json"},
    )
    headers = r.json()
    assert len(headers["Content-type"]) == 1
    assert headers["Content-type"][0] == "application/json"


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
    assert (
        r.json()["Authorization"][0] == f"Basic {base64.b64encode(b'foo:bar').decode()}"
    )


def test_timeout(server):
    with pytest.raises(requests.RequestsError):
        requests.get(str(server.url.copy_with(path="/slow_response")), timeout=0.1)


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
        requests.get(str(https_server.url), verify=True)


def test_verify_false(https_server):
    r = requests.get(str(https_server.url), verify=False)
    assert r.status_code == 200


def test_referer(server):
    r = requests.get(
        str(server.url.copy_with(path="/echo_headers")), referer="http://example.com"
    )
    headers = r.json()
    assert headers["Referer"][0] == "http://example.com"


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


def test_session_options(server):
    s = requests.Session()
    r = s.options(str(server.url))
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
    # request cookies should not be added to session cookiejar
    assert s.cookies.get("hello") is None


def test_cookie_domains(server):
    s = requests.Session()
    s.cookies.set("foo", "bar", domain="example.com")
    s.cookies.set("foo2", "bar", domain="127.0.0.1")
    # send requests with other cookies
    r = s.get(
        str(server.url.copy_with(path="/echo_cookies")), cookies={"hello": "world"}
    )
    cookies = r.json()
    # only specific domains should be there
    assert "foo" not in cookies
    assert cookies["foo2"] == "bar"
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


def test_cookies_after_redirect(server):
    s = requests.Session(debug=True)
    r = s.get(
        str(server.url.copy_with(path="/redirect_then_echo_cookies")),
        cookies={"foo": "bar"},
    )
    assert r.json()["foo"] == "bar"


def test_cookies_with_special_chars(server):
    s = requests.Session(debug=True)
    r = s.get(str(server.url.copy_with(path="/set_special_cookies")))
    assert s.cookies["foo"] == "bar space"
    r = s.get(str(server.url.copy_with(path="/echo_cookies")))
    assert r.json()["foo"] == "bar space"


# https://github.com/yifeikong/curl_cffi/issues/39
def test_post_body_cleaned(server):
    s = requests.Session()
    # POST with body
    r = s.post(str(server.url), json={"foo": "bar"})
    # GET request with echo_body
    assert s.curl._is_cert_set is False
    r = s.get(str(server.url.copy_with(path="/echo_body")))
    # ensure body is empty
    assert r.content == b""


# https://github.com/yifeikong/curl_cffi/issues/16
def test_session_with_headers(server):
    s = requests.Session()
    r = s.get(str(server.url), headers={"Foo": "bar"})
    r = s.get(str(server.url), headers={"Foo": "baz"})
    assert r.status_code == 200
