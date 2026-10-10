import pytest

from curl_cffi import requests
from curl_cffi.requests import AsyncSession, Response, Session
from curl_cffi.requests.exceptions import HTTPError


def test_request_response_hook(server):
    calls = []

    def hook(response, **kwargs):
        calls.append((response, kwargs))
        response.hook_called = True

    response = requests.get(str(server.url), hooks={"response": hook})

    assert calls[0][0] is response
    assert calls[0][1]["stream"] is False
    assert response.hook_called is True


def test_response_hooks_run_in_order_and_can_replace_response(server):
    replacement = Response()
    replacement.status_code = 299
    calls = []

    def replace(response, **kwargs):
        calls.append(("replace", response))
        return replacement

    def observe(response, **kwargs):
        calls.append(("observe", response))

    response = requests.get(str(server.url), hooks={"response": [replace, observe]})

    assert response is replacement
    assert calls[1] == ("observe", replacement)


def test_request_hooks_override_session_hooks(server):
    calls = []

    def session_hook(response, **kwargs):
        calls.append("session")

    def request_hook(response, **kwargs):
        calls.append("request")

    with Session(hooks={"response": session_hook}) as session:
        session.get(str(server.url))
        session.get(str(server.url), hooks={"response": request_hook})
        session.get(str(server.url), hooks={"response": []})

    assert calls == ["session", "request", "session"]


def test_session_hooks_can_be_appended(server):
    calls = []

    with Session() as session:
        session.hooks["response"].append(
            lambda response, **kwargs: calls.append(response)
        )
        response = session.get(str(server.url))

    assert calls == [response]


def test_unsupported_hook_event_is_rejected(server):
    with pytest.raises(ValueError, match="Only the 'response' hook is supported"):
        requests.get(str(server.url), hooks={"request": lambda response: None})


def test_response_hook_runs_before_raise_for_status(server):
    calls = []

    def hook(response, **kwargs):
        calls.append(response.status_code)

    with (
        Session(raise_for_status=True, hooks={"response": hook}) as session,
        pytest.raises(HTTPError),
    ):
        session.get(str(server.url.copy_with(path="/status/404")))

    assert calls == [404]


async def test_async_session_supports_sync_and_async_response_hooks(server):
    calls = []

    def sync_hook(response, **kwargs):
        calls.append(("sync", response))

    async def async_hook(response, **kwargs):
        calls.append(("async", response))
        return response

    async with AsyncSession() as session:
        response = await session.get(
            str(server.url), hooks={"response": [sync_hook, async_hook]}
        )

    assert calls == [("sync", response), ("async", response)]
