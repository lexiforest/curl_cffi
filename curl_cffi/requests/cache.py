from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Optional, Union
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .cookies import Cookies
from .headers import Headers
from .models import Request, Response

__all__ = [
    "CacheBackend",
    "CacheSpec",
    "FileCacheBackend",
    "normalize_cache_backend",
]


CacheSpec = Union["CacheBackend", int, timedelta]


def _encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _deserialize_headers(items: list[list[Optional[str]]]) -> Headers:
    return Headers([(key, value) for key, value in items])


def _har_headers(headers: Headers) -> list[dict[str, str]]:
    return [{"name": key, "value": value or ""} for key, value in headers.multi_items()]


def _har_query_string(url: str) -> list[dict[str, str]]:
    return [
        {"name": key, "value": value}
        for key, value in parse_qsl(urlsplit(url).query, keep_blank_values=True)
    ]


def _isoformat_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_har_timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def _response_cookies(headers: Headers) -> Cookies:
    cookies = Cookies()
    for set_cookie in headers.get_list("set-cookie"):
        if not set_cookie:
            continue
        try:
            parsed = SimpleCookie()
            parsed.load(set_cookie)
            for name, morsel in parsed.items():
                cookies.set(
                    name,
                    morsel.value,
                    domain=morsel.get("domain", ""),
                    path=morsel.get("path", "/"),
                    secure=bool(morsel.get("secure")),
                )
        except Exception:
            continue
    return cookies


class CacheBackend(ABC):
    def __init__(
        self,
        *,
        expires: timedelta,
        methods: Sequence[str] | None = None,
        ignored: Sequence[str] | None = None,
    ) -> None:
        if expires.total_seconds() < 0:
            raise ValueError("expires must be >= 0")

        self.expires = expires
        self.expires_seconds = expires.total_seconds()
        self.methods = frozenset(method.upper() for method in (methods or ("GET",)))
        self.ignored = frozenset(ignored or ())

    def should_cache_request(
        self,
        request: Request,
        *,
        stream: bool = False,
        content_callback: Any = None,
    ) -> bool:
        """
        XXX: streamed content is not cached.
        """
        return (
            request.method.upper() in self.methods
            and not stream
            and content_callback is None
        )

    def should_store_response(self, response: Response) -> bool:
        return response.ok

    def get(
        self,
        request: Request,
        response_class: type[Response] = Response,
    ) -> Response | None:
        payload = self._read_payload(self._cache_key(request))
        if payload is None:
            return None

        entry = payload["log"]["entries"][0]
        created_at = _parse_har_timestamp(entry["startedDateTime"])
        if self.expires_seconds and (time.time() - created_at) > self.expires_seconds:
            self.delete(request)
            return None

        return self._response_from_payload(request, payload, response_class)

    def set(self, request: Request, response: Response) -> None:
        if not self.should_store_response(response):
            return
        key = self._cache_key(request)
        payload = self._payload_from_response(response)
        self._write_payload(key, payload)

    def delete(self, request: Request) -> None:
        self._delete_payload(self._cache_key(request))

    def _cache_key(self, request: Request) -> str:
        normalized = self._normalized_url(request.url)
        body_hash = hashlib.sha256(request.body or b"").hexdigest()
        raw_key = json.dumps(
            {"method": request.method.upper(), "url": normalized, "body": body_hash},
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def _normalized_url(self, url: str) -> str:
        parts = urlsplit(url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in self.ignored
        ]
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                parts.path,
                urlencode(query, doseq=True),
                "",
            )
        )

    def _payload_from_response(self, response: Response) -> dict[str, Any]:
        default_encoding = response.default_encoding
        if not isinstance(default_encoding, str):
            default_encoding = "utf-8"

        return {
            "log": {
                "version": "1.2",
                "creator": {"name": "curl_cffi", "version": "cache"},
                "entries": [
                    {
                        "startedDateTime": _isoformat_now(),
                        "time": response.elapsed.total_seconds() * 1000,
                        "request": {
                            "method": (
                                response.request.method if response.request else ""
                            ),
                            "url": response.request.url if response.request else "",
                            "httpVersion": "",
                            "cookies": [],
                            "headers": (
                                _har_headers(response.request.headers)
                                if response.request
                                else []
                            ),
                            "queryString": (
                                _har_query_string(response.request.url)
                                if response.request
                                else []
                            ),
                            "headersSize": -1,
                            "bodySize": (
                                len(response.request.body)
                                if response.request and response.request.body
                                else 0
                            ),
                            **(
                                {
                                    "postData": {
                                        "mimeType": (
                                            response.request.headers.get(
                                                "Content-Type",
                                                "application/octet-stream",
                                            )
                                            if response.request
                                            else "application/octet-stream"
                                        ),
                                        "text": _encode_bytes(response.request.body),
                                        "encoding": "base64",
                                    }
                                }
                                if (
                                    response.request
                                    and response.request.body is not None
                                )
                                else {}
                            ),
                        },
                        "response": {
                            "status": response.status_code,
                            "statusText": response.reason,
                            "httpVersion": str(response.http_version),
                            "cookies": [],
                            "headers": _har_headers(response.headers),
                            "content": {
                                "size": len(response.content),
                                "mimeType": response.headers.get(
                                    "Content-Type",
                                    "application/octet-stream",
                                ),
                                "text": _encode_bytes(response.content),
                                "encoding": "base64",
                            },
                            "redirectURL": response.redirect_url,
                            "headersSize": response.header_size,
                            "bodySize": response.download_size,
                            "_curl_cffi": {
                                "url": response.url,
                                "default_encoding": default_encoding,
                                "redirect_count": response.redirect_count,
                                "primary_ip": response.primary_ip,
                                "primary_port": response.primary_port,
                                "local_ip": response.local_ip,
                                "local_port": response.local_port,
                                "download_size": response.download_size,
                                "upload_size": response.upload_size,
                                "header_size": response.header_size,
                                "request_size": response.request_size,
                                "response_size": response.response_size,
                            },
                        },
                        "cache": {},
                        "timings": {
                            "send": 0,
                            "wait": response.elapsed.total_seconds() * 1000,
                            "receive": 0,
                        },
                    }
                ],
            }
        }

    def _response_from_payload(
        self,
        request: Request,
        payload: dict[str, Any],
        response_class: type[Response],
    ) -> Response:
        entry = payload["log"]["entries"][0]
        har_response = entry["response"]
        extra = har_response.get("_curl_cffi", {})
        header_items = [
            [item.get("name", ""), item.get("value", "")]
            for item in har_response["headers"]
        ]
        headers = _deserialize_headers(header_items)
        try:
            response = response_class(request=request)
        except TypeError:
            response = response_class()
            response.request = request
        response.url = extra.get("url", request.url)
        response.content = _decode_bytes(har_response["content"]["text"])
        response.status_code = int(har_response["status"])
        response.reason = har_response.get("statusText", "")
        response.ok = 200 <= response.status_code < 400
        response.headers = headers
        response.cookies = _response_cookies(response.headers)
        response.default_encoding = extra.get("default_encoding", "utf-8")
        response.elapsed = timedelta(milliseconds=float(entry.get("time", 0.0)))
        response.redirect_count = int(extra.get("redirect_count", 0))
        response.redirect_url = har_response.get("redirectURL", "")
        response.http_version = int(har_response.get("httpVersion", 0) or 0)
        response.primary_ip = extra.get("primary_ip", "")
        response.primary_port = int(extra.get("primary_port", 0))
        response.local_ip = extra.get("local_ip", "")
        response.local_port = int(extra.get("local_port", 0))
        response.download_size = int(
            extra.get(
                "download_size",
                har_response["content"].get("size", len(response.content)),
            )
        )
        response.upload_size = int(extra.get("upload_size", 0))
        response.header_size = int(extra.get("header_size", 0))
        response.request_size = int(extra.get("request_size", 0))
        response.response_size = int(
            extra.get("response_size", response.download_size + response.header_size)
        )
        return response

    @abstractmethod
    def _read_payload(self, key: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def _write_payload(self, key: str, payload: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def _delete_payload(self, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError


class FileCacheBackend(CacheBackend):
    def __init__(
        self,
        *,
        expires: timedelta,
        path: str | os.PathLike[str] = "/tmp",
        methods: Sequence[str] | None = None,
        ignored: Sequence[str] | None = None,
    ) -> None:
        super().__init__(expires=expires, methods=methods, ignored=ignored)
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, key: str) -> Path:
        return self.path / f"{key}.json"

    def _iter_cache_files(self) -> list[Path]:
        return [
            file_path
            for file_path in self.path.glob("*.json")
            if len(file_path.stem) == 64
            and all(char in "0123456789abcdef" for char in file_path.stem)
        ]

    def _read_payload(self, key: str) -> dict[str, Any] | None:
        file_path = self._file_path(key)
        try:
            with file_path.open("r", encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError, json.JSONDecodeError):
            with suppress(FileNotFoundError):
                file_path.unlink()
            return None
        try:
            entries = payload["log"]["entries"]
            if not entries:
                raise ValueError("empty HAR entries")
            _parse_har_timestamp(entries[0]["startedDateTime"])
            return payload
        except (KeyError, TypeError, ValueError):
            with suppress(FileNotFoundError):
                file_path.unlink()
            return None

    def _write_payload(self, key: str, payload: dict[str, Any]) -> None:
        file_path = self._file_path(key)
        tmp_path = file_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, separators=(",", ":"))
        os.replace(tmp_path, file_path)

    def _delete_payload(self, key: str) -> None:
        with suppress(FileNotFoundError):
            self._file_path(key).unlink()

    def clear(self) -> None:
        for file_path in self._iter_cache_files():
            with suppress(FileNotFoundError):
                file_path.unlink()


def normalize_cache_backend(cache: CacheSpec | None) -> CacheBackend | None:
    if cache is None:
        return None
    if isinstance(cache, CacheBackend):
        return cache
    if isinstance(cache, int):
        cache = timedelta(seconds=cache)
    if isinstance(cache, timedelta):
        return FileCacheBackend(expires=cache)
    raise TypeError("cache must be a CacheBackend, int, timedelta, or None")
