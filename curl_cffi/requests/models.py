import warnings
from json import loads
from typing import Optional

from .. import Curl
from .headers import Headers
from .cookies import Cookies
from .errors import RequestsError


class Request:
    def __init__(self, url: str, headers: Headers, method: str):
        self.url = url
        self.headers = headers
        self.method = method


class Response:
    """Contains information the server sends.

    Attributes:
        url: url used in the request.
        content: response body in bytes.
        status_code: http status code.
        reason: http response reason, such as OK, Not Found.
        ok: is status_code in [200, 400)?
        headers: response headers.
        cookies: response cookies.
        elapsed: how many seconds the request cost.
        encoding: http body encoding.
        charset: alias for encoding.
        redirect_count: how many redirects happened.
        redirect_url: the final redirected url.
        http_version: http version used.
        history: history redirections, only headers are available.
    """
    def __init__(self, curl: Optional[Curl] = None, request: Optional[Request] = None):
        self.curl = curl
        self.request = request
        self.url = ""
        self.content = b""
        self.status_code = 200
        self.reason = "OK"
        self.ok = True
        self.headers = Headers()
        self.cookies = Cookies()
        self.elapsed = 0.0
        self.encoding = "utf-8"
        self.charset = self.encoding
        self.redirect_count = 0
        self.redirect_url = ""
        self.http_version = 0
        self.history = []

    @property
    def text(self) -> str:
        return self.content.decode(self.charset)

    def raise_for_status(self):
        if not self.ok:
            raise RequestsError(f"HTTP Error {self.status_code}: {self.reason}")

    def json(self, **kw):
        return loads(self.content, **kw)

    def close(self):
        warnings.warn("Deprecated, use Session.close")
