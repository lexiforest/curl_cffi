import base64
from urllib.parse import parse_qs, urlparse

import pytest

from curl_cffi import Headers, PreparedRequest, Request
from curl_cffi.requests import AsyncSession, Session


def test_request_prepare():
    request = Request(
        "post",
        "https://example.com/resource",
        params={"page": "1"},
        data={"hello": "world"},
    )

    prepared = request.prepare()

    assert isinstance(prepared, PreparedRequest)
    assert prepared.method == "POST"
    assert parse_qs(urlparse(prepared.url).query) == {"page": ["1"]}
    assert prepared.body == b"hello=world"
    assert prepared.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_request_legacy_constructor_order():
    request = Request(
        "https://example.com/resource",
        Headers({"Content-Type": "text/plain"}),
        "POST",
        b"body",  # type: ignore[arg-type]
    )

    prepared = request.prepare()

    assert prepared.method == "POST"
    assert prepared.url == "https://example.com/resource"
    assert prepared.body == b"body"


def test_prepare_request_applies_session_settings():
    authorization = base64.b64encode(b"user:password").decode()
    with Session(
        base_url="https://example.com/api/",
        params={"session": "yes"},
        headers={"X-Session": "yes", "X-Override": "session"},
        cookies={"session": "yes"},
        auth=("user", "password"),
    ) as session:
        prepared = session.prepare_request(
            Request(
                "GET",
                "resource",
                params={"request": "yes"},
                headers={"X-Request": "yes", "X-Override": "request"},
                cookies={"request": "yes"},
            )
        )

    assert prepared.url.startswith("https://example.com/api/resource?")
    assert parse_qs(urlparse(prepared.url).query) == {
        "session": ["yes"],
        "request": ["yes"],
    }
    assert prepared.headers["X-Session"] == "yes"
    assert prepared.headers["X-Request"] == "yes"
    assert prepared.headers["X-Override"] == "request"
    assert prepared.headers["Cookie"] in (
        "session=yes; request=yes",
        "request=yes; session=yes",
    )
    assert prepared.headers["Authorization"] == f"Basic {authorization}"


def test_build_request_content_and_data_are_mutually_exclusive():
    with (
        Session() as session,
        pytest.raises(TypeError, match="both 'content' and 'data'"),
    ):
        session.build_request(
            "POST", "https://example.com", content=b"one", data=b"two"
        )


def test_send_uses_mutated_prepared_request(server):
    with Session() as session:
        prepared = session.build_request(
            "GET",
            str(server.url),
        )
        prepared.method = "POST"
        prepared.url = str(server.url.copy_with(path="/echo_body"))
        prepared.content = b'{"hello":"world"}'
        prepared.headers["Content-Type"] = "application/json"

        response = session.send(prepared)

    assert response.content == b'{"hello":"world"}'
    assert response.request is prepared
    assert response.request.method == "POST"
    assert response.request.body == b'{"hello":"world"}'


def test_send_uses_prepared_cookies(server):
    with Session(cookies={"session": "yes"}) as session:
        prepared = session.prepare_request(
            Request(
                "GET",
                str(server.url.copy_with(path="/echo_headers")),
                cookies={"request": "yes"},
            )
        )

        response = session.send(prepared)

    assert response.json()["Cookie"] in (
        ["session=yes; request=yes"],
        ["request=yes; session=yes"],
    )


def test_send_uses_mutated_headers(server):
    with Session() as session:
        prepared = session.build_request(
            "GET",
            str(server.url.copy_with(path="/echo_headers")),
            headers={"User-Agent": "before"},
        )
        prepared.headers["User-Agent"] = "after"

        response = session.send(prepared)

    assert response.json()["User-agent"] == ["after"]


def test_regular_request_exposes_prepared_request(server):
    with Session() as session:
        response = session.post(
            str(server.url.copy_with(path="/echo_body")), data=b"body"
        )

    assert isinstance(response.request, PreparedRequest)
    assert isinstance(response.request, Request)
    assert response.request.method == "POST"
    assert response.request.body == b"body"


def test_send_accepts_transport_options(server):
    with Session() as session:
        prepared = session.build_request(
            "GET", str(server.url.copy_with(path="/redirect_301"))
        )

        response = session.send(prepared, allow_redirects=False)

    assert response.status_code == 301


def test_send_streams_prepared_request(server):
    with Session() as session:
        prepared = session.build_request(
            "GET", str(server.url.copy_with(path="/stream")), params={"n": "2"}
        )

        response = session.send(prepared, stream=True)
        chunks = list(response.iter_content())

    assert len(chunks) == 2


def test_send_requires_prepared_request():
    with Session() as session, pytest.raises(TypeError, match="PreparedRequest"):
        session.send(Request("GET", "https://example.com"))  # type: ignore[arg-type]


async def test_async_send_uses_prepared_request(server):
    async with AsyncSession() as session:
        prepared = session.build_request(
            "POST",
            str(server.url.copy_with(path="/echo_body")),
            json={"hello": "world"},
        )

        response = await session.send(prepared)

    assert response.content == b'{"hello":"world"}'
    assert response.request is prepared
