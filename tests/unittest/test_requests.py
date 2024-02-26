import base64
import time
from io import BytesIO
import json

import pytest

from curl_cffi import requests, CurlOpt
from curl_cffi.const import CurlECode, CurlInfo
from curl_cffi.requests.errors import SessionClosed


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


def test_post_large_body(server):
    bar = "a" * 100000
    r = requests.post(str(server.url.copy_with(path="/echo_body")), json={"foo": bar})
    assert r.status_code == 200
    assert r.json()["foo"] == bar


def test_post_str(server):
    r = requests.post(
        str(server.url.copy_with(path="/echo_body")), data='{"foo": "bar"}'
    )
    assert r.status_code == 200
    assert r.content == b'{"foo": "bar"}'


def test_post_no_body(server):
    r = requests.post(str(server.url), headers={"Content-Type": "application/json"})
    assert r.status_code == 200
    r = requests.post(str(server.url), headers={"Content-Length": "0"})
    assert r.status_code == 200


def test_post_json(server):
    r = requests.post(str(server.url.copy_with(path="/echo_body")), json={"foo": "bar"})
    assert r.status_code == 200
    assert r.content == b'{"foo":"bar"}'
    r = requests.post(str(server.url.copy_with(path="/echo_body")), json={})
    assert r.status_code == 200
    assert r.content == b"{}"


def test_post_redirect_to_get(server):
    url = str(server.url.copy_with(path="/redirect_then_echo_headers"))
    r = requests.post(url, data={"foo": "bar"}, allow_redirects=True, debug=True)
    headers = r.json()
    # print(headers)
    assert headers.get("Content-length") is None


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


def test_params(server):
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


def test_charset_parse(server):
    r = requests.get( str(server.url.copy_with(path="/gbk")))
    assert r.charset == "gbk"


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


def test_secure_cookies(server):
    with pytest.warns(UserWarning, match="changed"):
        r = requests.get(
            str(server.url.copy_with(path="/echo_cookies")),
            cookies={"__Secure-foo": "bar", "__Host-hello": "world"},
        )
        cookies = r.json()
        assert cookies["__Secure-foo"] == "bar"
        assert cookies["__Host-hello"] == "world"


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


def test_session_timeout(server):
    with pytest.raises(requests.RequestsError):
        requests.Session(timeout=0.1).get(str(server.url.copy_with(path="/slow_response")))


def test_post_timeout(server):
    with pytest.raises(requests.RequestsError):
        requests.post(str(server.url.copy_with(path="/slow_response")), timeout=0.1)


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


def test_too_many_redirects(server):
    with pytest.raises(requests.RequestsError) as e:
        requests.get(str(server.url.copy_with(path="/redirect_loop")), max_redirects=2)
    assert e.value.code == CurlECode.TOO_MANY_REDIRECTS
    assert e.value.response.status_code == 301  # type: ignore


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
    # XXX request cookies will always be added to the entire session
    # request cookies should not be added to session cookiejar
    # assert s.cookies.get("hello") is None

    # but you can override
    r = s.get(
        str(server.url.copy_with(path="/echo_cookies")), cookies={"foo": "notbar"}
    )
    cookies = r.json()
    assert cookies["foo"] == "notbar"


def test_delete_cookies(server):
    s = requests.Session()
    s.get(str(server.url.copy_with(path="/set_cookies")))
    assert s.cookies["foo"] == "bar"
    s.get(str(server.url.copy_with(path="/delete_cookies")))
    assert not s.cookies.get("foo")


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
    s = requests.Session()
    r = s.get(str(server.url.copy_with(path="/set_special_cookies")))
    assert s.cookies["foo"] == "bar space"
    r = s.get(str(server.url.copy_with(path="/echo_cookies")))
    assert r.json()["foo"] == "bar space"


# https://github.com/yifeikong/curl_cffi/issues/119
def test_cookies_mislead_by_host(server):
    s = requests.Session(debug=True)
    s.curl.setopt(CurlOpt.RESOLVE, ["example.com:8000:127.0.0.1"])
    s.cookies.set("foo", "bar")
    print("URL is: ", str(server.url))
    # TODO replace hard-coded url with server.url.replace(host="example.com")
    r = s.get("http://example.com:8000", headers={"Host": "example.com"})
    r = s.get(str(server.url.copy_with(path="/echo_cookies")))
    assert r.json()["foo"] == "bar"


# https://github.com/yifeikong/curl_cffi/issues/119
def test_cookies_redirect_to_another_domain(server):
    s = requests.Session()
    s.curl.setopt(CurlOpt.RESOLVE, ["google.com:8000:127.0.0.1"])
    s.cookies.set("foo", "google.com", domain="google.com")
    r = s.get(
        str(server.url.copy_with(path="/redirect_to")),
        params={"to": "http://google.com:8000/echo_cookies"},
    )
    cookies = r.json()
    assert cookies["foo"] == "google.com"


# https://github.com/yifeikong/curl_cffi/issues/119
def test_cookies_wo_hostname_redirect_to_another_domain(server):
    s = requests.Session(debug=True)
    s.curl.setopt(
        CurlOpt.RESOLVE,
        [
            "example.com:8000:127.0.0.1",
            "google.com:8000:127.0.0.1",
        ],
    )
    s.cookies.set("foo", "bar")
    s.cookies.set("hello", "world", domain="google.com")
    r = s.get(
        # str(server.url.copy_with(path="/redirect_to")),
        "http://example.com:8000/redirect_to",
        params={"to": "http://google.com:8000/echo_cookies"},
    )
    cookies = r.json()
    # cookies without domains are bound to the first domain, which is example.com in this case.
    assert len(cookies) == 1
    assert cookies["hello"] == "world"


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


# https://github.com/yifeikong/curl_cffi/pull/171
def test_session_with_hostname_proxies(server, proxy_server):
    proxies = {
        f'all://{server.url.host}': f'http://{proxy_server.flags.hostname}:{proxy_server.flags.port}'
    }
    s = requests.Session(proxies=proxies)
    url = str(server.url.copy_with(path="/echo_headers"))
    r = s.get(url)
    assert r.text == 'Hello from man in the middle'


# https://github.com/yifeikong/curl_cffi/pull/171
def test_session_with_http_proxies(server, proxy_server):
    proxies = {
        'http': f'http://{proxy_server.flags.hostname}:{proxy_server.flags.port}'
    }
    s = requests.Session(proxies=proxies)
    url = str(server.url.copy_with(path="/echo_headers"))
    r = s.get(url)
    assert r.text == 'Hello from man in the middle'


# https://github.com/yifeikong/curl_cffi/pull/171
def test_session_with_all_proxies(server, proxy_server):
    proxies = {
        'all': f'http://{proxy_server.flags.hostname}:{proxy_server.flags.port}'
    }
    s = requests.Session(proxies=proxies)
    url = str(server.url.copy_with(path="/echo_headers"))
    r = s.get(url)
    assert r.text == 'Hello from man in the middle'


# https://github.com/yifeikong/curl_cffi/issues/222
def test_closed_session_throws_error():
    with requests.Session() as s:
        pass

    with pytest.raises(SessionClosed):
        s.get('https://example.com')

    with pytest.raises(SessionClosed):
        s.post('https://example.com')

    with pytest.raises(SessionClosed):
        s.put('https://example.com')

    with pytest.raises(SessionClosed):
        s.delete('https://example.com')

    with pytest.raises(SessionClosed):
        s.options('https://example.com')

    with pytest.raises(SessionClosed):
        s.head('https://example.com')

    with pytest.raises(SessionClosed):
        s.patch('https://example.com')

    with pytest.raises(SessionClosed):
        s.ws_connect('wss://example.com')


def test_stream_iter_content(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/stream"))
        with s.stream("GET", url, params={"n": "20"}) as r:
            for chunk in r.iter_content():
                assert b"path" in chunk


def test_stream_iter_content_break(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/stream"))
        with s.stream("GET", url, params={"n": "20"}) as r:
            for idx, chunk in enumerate(r.iter_content()):
                assert b"path" in chunk
                if idx == 3:
                    break
            assert r.status_code == 200


def test_stream_iter_lines(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/stream"))
        with s.stream("GET", url, params={"n": "20"}) as r:
            for chunk in r.iter_lines():
                data = json.loads(chunk)
                assert data["path"] == "/stream"


def test_stream_status_code(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/stream"))
        with s.stream("GET", url, params={"n": "20"}) as r:
            assert r.status_code == 200


def test_stream_empty_body(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/empty_body"))
        with s.stream("GET", url) as r:
            assert r.status_code == 200


# def test_stream_large_body(server):
#     with requests.Session() as s:
#         url = str(server.url.copy_with(path="/stream"))
#         with s.stream("GET", url, params={"n": "100000"}) as r:
#             for chunk in r.iter_lines():
#                 data = json.loads(chunk)
#                 assert data["path"] == "/stream"
#                 # print(data["path"])
#             assert r.status_code == 200


def test_stream_incomplete_read(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/incomplete_read"))
        with pytest.raises(requests.RequestsError) as e:
            with s.stream("GET", url) as r:
                for _ in r.iter_content():
                    continue
        assert e.value.code == CurlECode.PARTIAL_FILE


def test_stream_incomplete_read_without_close(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/incomplete_read"))
        with pytest.raises(requests.RequestsError) as e:
            r = s.get(url, stream=True)

            # The error will only be raised when you try to read it.
            for _ in r.iter_content():
                continue

        assert e.value.code == CurlECode.PARTIAL_FILE


def test_stream_redirect_loop(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/redirect_loop"))
        with pytest.raises(requests.RequestsError) as e:
            with s.stream("GET", url, max_redirects=2):
                pass
        assert e.value.code == CurlECode.TOO_MANY_REDIRECTS
        assert e.value.response.status_code == 301  # type: ignore


def test_stream_redirect_loop_without_close(server):
    with requests.Session() as s:
        url = str(server.url.copy_with(path="/redirect_loop"))
        with pytest.raises(requests.RequestsError) as e:
            # if the error happens receiving header, it's raised right away
            s.get(url, max_redirects=2, stream=True)

        assert e.value.code == CurlECode.TOO_MANY_REDIRECTS
        assert e.value.response.status_code == 301  # type: ignore


def test_stream_auto_close_plain(server):
    s = requests.Session()
    url = str(server.url.copy_with(path="/stream"))
    s.get(url, stream=True)
    url = str(server.url.copy_with(path="/"))
    s.get(url)


def test_stream_auto_close_with_content_errors(server):
    s = requests.Session()

    # Silently fails, since the content is not read at all.
    url = str(server.url.copy_with(path="/incomplete_read"))
    s.get(url, stream=True)

    url = str(server.url.copy_with(path="/"))
    s.get(url, stream=True)


def test_stream_auto_close_with_header_errors(server):
    s = requests.Session()

    url = str(server.url.copy_with(path="/redirect_loop"))
    with pytest.raises(requests.RequestsError) as e:
        s.get(url, max_redirects=2, stream=True)
    assert e.value.code == CurlECode.TOO_MANY_REDIRECTS
    assert e.value.response.status_code == 301  # type: ignore

    url = str(server.url.copy_with(path="/"))
    s.get(url, stream=True)


def test_stream_options_persist(server):
    s = requests.Session()

    # set here instead of when requesting
    s.curl.setopt(CurlOpt.USERAGENT, b"foo/1.0")

    url = str(server.url.copy_with(path="/echo_headers"))
    r = s.get(url, stream=True)
    buffer = []
    for line in r.iter_lines():
        buffer.append(line)
    data = json.loads(b"".join(buffer))
    assert data["User-agent"][0] == "foo/1.0"


@pytest.mark.skip(reason="External url unstable")
def test_stream_close_early(server):
    s = requests.Session()
    # url = str(server.url.copy_with(path="/large"))
    # from http://xcal1.vodafone.co.uk/
    url = "http://212.183.159.230/200MB.zip"
    r = s.get(url, max_recv_speed=1024 * 1024, stream=True)
    counter = 0
    start = time.time()
    for _ in r.iter_content():
        counter += 1
        if counter > 10:
            break
    r.close()
    end = time.time()
    assert end - start < 50


@pytest.mark.skip(reason="External url unstable")
def test_max_recv_speed(server):
    s = requests.Session()
    s.curl.setopt(CurlOpt.BUFFERSIZE, 1024 * 1024)
    url = str(server.url.copy_with(path="/large"))
    # from http://xcal1.vodafone.co.uk/
    url = "http://212.183.159.230/200MB.zip"
    start = time.time()
    r = s.get(url, max_recv_speed=10 * 1024 * 1024)
    end = time.time()
    # assert len(r.content) == 20 * 1024 * 1024
    assert end - start > 10


def test_curl_infos(server):
    s = requests.Session(curl_infos=[CurlInfo.PRIMARY_IP])

    r = s.get(str(server.url))

    assert r.infos[CurlInfo.PRIMARY_IP] == b"127.0.0.1"
