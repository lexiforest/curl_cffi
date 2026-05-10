"""Unit tests for ``curl_cffi.requests.models``.

These tests construct ``Response`` directly without a server so they exercise
pure-Python parsing helpers (e.g. ``Response.json``) in isolation.
"""

from decimal import Decimal

import pytest

from curl_cffi.requests.models import Response

try:
    import orjson  # noqa: F401

    _HAS_ORJSON = True
except ImportError:
    _HAS_ORJSON = False


def _make_response(content: bytes) -> Response:
    r = Response()
    r.content = content
    return r


def test_json_default_parses_content():
    r = _make_response(b'{"foo": 1, "bar": "baz"}')
    assert r.json() == {"foo": 1, "bar": "baz"}


@pytest.mark.skipif(
    not _HAS_ORJSON, reason="behavior under test only triggers when orjson is installed"
)
def test_json_kwargs_without_flag_raises_when_orjson_present():
    """Forwarding kwargs without ``use_stdlib_json=True`` must still raise so
    that existing call sites get a clear failure rather than silent behaviour
    drift. See #639."""
    r = _make_response(b'{"price": 1.5}')
    with pytest.raises(TypeError):
        r.json(parse_float=Decimal)


def test_json_use_stdlib_json_true_accepts_kwargs():
    """Opt-out flag forwards kwargs to ``json.loads`` and parses correctly."""
    r = _make_response(b'{"price": 1.5}')
    parsed = r.json(use_stdlib_json=True, parse_float=Decimal)
    assert parsed == {"price": Decimal("1.5")}
    assert isinstance(parsed["price"], Decimal)


def test_json_use_stdlib_json_true_without_kwargs():
    """Opt-out flag works on its own (no kwargs) — just exercises the stdlib
    code path; result must match the default path."""
    r = _make_response(b'{"foo": 1, "bar": "baz"}')
    assert r.json(use_stdlib_json=True) == r.json()


def test_json_use_stdlib_json_false_default_remains_orjson_path():
    """Explicit ``use_stdlib_json=False`` reproduces the unchanged default,
    which is the same instance ``orjson.loads`` (or stdlib if orjson is
    missing). The output is identical to ``r.json()``."""
    r = _make_response(b'{"foo": 1}')
    assert r.json(use_stdlib_json=False) == r.json()


@pytest.mark.parametrize(
    "content,kwargs,expected",
    [
        (b'{"n": 1.5}', {"parse_float": Decimal}, {"n": Decimal("1.5")}),
        (b'{"n": 100}', {"parse_int": float}, {"n": 100.0}),
        (
            b'{"n": 9999999999999999999}',
            {"parse_int": str},
            {"n": "9999999999999999999"},
        ),
    ],
)
def test_json_use_stdlib_json_forwards_supported_kwargs(content, kwargs, expected):
    """``json.loads`` supports ``parse_float`` / ``parse_int`` / ``parse_constant``;
    the opt-out path must forward them."""
    r = _make_response(content)
    assert r.json(use_stdlib_json=True, **kwargs) == expected
