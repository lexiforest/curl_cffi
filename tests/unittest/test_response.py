import json
import sys

import pytest

from curl_cffi.requests import Response
from curl_cffi.requests import models


@pytest.fixture
def response():
    response = Response()
    response.content = json.dumps(
        {"data": {"users": [{"name": "Alice"}, {"name": "Bob"}]}}
    ).encode()
    return response


def test_json_path(response):
    assert response.json(path=".data.users") == response.json()["data"]["users"]


def test_json_path_first_match(response):
    assert response.json(path="$.data.users[*].name") == "Alice"


def test_json_path_default(response):
    default = []
    assert response.json(path=".missing", default=default) is default
    assert response.json(path=".missing") is None


@pytest.mark.parametrize("value", [None, []])
def test_json_path_falsey_value(value):
    response = Response()
    response.content = json.dumps({"value": value}).encode()
    assert response.json(path=".value", default="fallback") == value


@pytest.mark.parametrize("path", ["", "$.data["])
def test_json_path_invalid(response, path):
    with pytest.raises(ValueError):
        response.json(path=path, default=[])


def test_json_path_invalid_type(response):
    with pytest.raises(TypeError, match="path must be a string"):
        response.json(path=1)


def test_json_path_invalid_json(response):
    response.content = b"invalid json"
    with pytest.raises(ValueError):
        response.json(path=".data", default=[])


def test_json_path_optional_dependency(response, monkeypatch):
    monkeypatch.setitem(sys.modules, "jsonpath_ng.ext", None)
    assert response.json(default="unused")["data"]["users"][0]["name"] == "Alice"
    with pytest.raises(ImportError, match=r"curl_cffi\[extra\]"):
        response.json(path=".data", default=[])


def test_json_path_charset():
    response = Response()
    response.headers["Content-Type"] = "application/json; charset=gb2312"
    response.content = '{"name": "中文"}'.encode("gb2312")
    assert response.json(path=".name") == "中文"


def test_json_path_decoder_kwargs(monkeypatch):
    def loads(content):
        return json.loads(content)

    monkeypatch.setattr(models, "loads", loads)
    response = Response()
    response.content = b'{"value": 1.5}'
    assert response.json(path=".value", parse_float=str) == "1.5"
    assert response.json(parse_float=str) == {"value": "1.5"}
