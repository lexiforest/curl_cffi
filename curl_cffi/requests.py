import re
from functools import partial
from http.cookies import SimpleCookie
from io import BytesIO
from json import dumps, loads
from typing import IO, Any, Dict, List, Optional, Tuple, Union, cast
from urllib.parse import ParseResult, parse_qsl, unquote, urlencode, urlparse
from enum import Enum

from . import Curl, CurlError, CurlInfo, CurlOpt
from .headers import Headers


class RequestsError(CurlError):
    pass


class BrowserType(str, Enum):
    edge99 = "edge99"
    edge101 = "edge101"
    chrome99 = "chrome99"
    chrome100 = "chrome100"
    chrome101 = "chrome101"
    chrome104 = "chrome104"
    chrome99_android = "chrome99_android"
    safari15_3 = "safari15_3"
    safari15_5 = "safari15_5"

    @classmethod
    def has(cls, item):
        return item in cls.__members__


def _update_url_params(url: str, params: Dict) -> str:
    """Add GET params to provided URL being aware of existing.

    :param url: string of target URL
    :param params: dict containing requested params to be added
    :return: string with updated URL

    >> url = 'http://stackoverflow.com/test?answers=true'
    >> new_params = {'answers': False, 'data': ['some','values']}
    >> _update_url_params(url, new_params)
    'http://stackoverflow.com/test?data=some&data=values&answers=false'
    """
    # Unquoting URL first so we don't loose existing args
    url = unquote(url)
    # Extracting url info
    parsed_url = urlparse(url)
    # Extracting URL arguments from parsed URL
    get_args = parsed_url.query
    # Converting URL arguments to dict
    parsed_get_args = dict(parse_qsl(get_args))
    # Merging URL arguments dict with new params
    parsed_get_args.update(params)

    # Bool and Dict values should be converted to json-friendly values
    # you may throw this part away if you don't like it :)
    parsed_get_args.update(
        {k: dumps(v) for k, v in parsed_get_args.items() if isinstance(v, (bool, dict))}
    )

    # Converting URL argument to proper query string
    encoded_get_args = urlencode(parsed_get_args, doseq=True)
    # Creating new parsed result object based on provided with new
    # URL arguments. Same thing happens inside of urlparse.
    new_url = ParseResult(
        parsed_url.scheme,
        parsed_url.netloc,
        parsed_url.path,
        parsed_url.params,
        encoded_get_args,
        parsed_url.fragment,
    ).geturl()

    return new_url


class Response:
    def __init__(self, curl: Curl):
        self._curl = curl
        self.url = ""
        self.content = b""
        self.status_code = 200
        self.reason = "OK"
        self.ok = True
        self.headers = Headers()
        self.cookies = SimpleCookie()
        self.elapsed = 0.0
        self.encoding = "utf-8"
        self.charset = self.encoding
        self.redirect_count = 0
        self.redirect_url = ""

    @property
    def text(self) -> str:
        return self.content.decode(self.charset)

    def raise_for_status(self):
        if not self.ok:
            raise RequestsError(f"HTTP Error {self.status_code}: {self.reason}")

    def json(self, **kw):
        return loads(self.content, **kw)

    def close(self):
        self._curl.close()


def request(
    method: str,
    url: str,
    params: Optional[dict] = None,
    data: Optional[Union[Dict[str, str], BytesIO, bytes]] = None,
    json: Optional[dict] = None,
    headers: Optional[Union[Dict[str, str], List[str], Headers]] = None,
    cookies: Optional[Union[Dict[str, str], SimpleCookie]] = None,
    files: Optional[Dict] = None,
    auth: Optional[Tuple[str, str]] = None,
    timeout: Union[float, Tuple[float, float]] = 30,
    allow_redirects: bool = True,
    max_redirects: int = -1,
    proxies: Optional[dict] = None,
    verify: bool = True,
    referer: Optional[str] = None,
    accept_encoding: Optional[str] = "gzip, deflate, br",
    impersonate: Optional[Union[str, BrowserType]] = None,
) -> Response:

    c = Curl()

    # method
    c.setopt(CurlOpt.CUSTOMREQUEST, method.encode())

    # url
    if params:
        url = _update_url_params(url, params)
    c.setopt(CurlOpt.URL, url.encode())

    # data/body/json
    if isinstance(data, dict):
        body = urlencode(data).encode()
    elif isinstance(data, BytesIO):
        body = data.read()
    elif isinstance(data, bytes):
        body = data
    elif data is None:
        body = b""
    else:
        raise TypeError("data must be dict, BytesIO or bytes")
    if json:
        body = dumps(json).encode()
    if body:
        c.setopt(CurlOpt.POSTFIELDS, body)
        c.setopt(CurlOpt.POSTFIELDSIZE, len(body))  # necessary if body contains '\0'

    # headers
    if isinstance(headers, list):
        header_lines = headers
    else:
        if isinstance(headers, dict):
            h = Headers(headers)
        elif isinstance(headers, Headers):
            h = headers
        elif headers is None:
            h = Headers()
        else:
            raise TypeError("headers must be a dict, list or Headers")
        header_lines = []
        for k, v in h.multi_items():
            header_lines.append(f"{k}: {v}")
    if json:
        for idx, line in enumerate(header_lines):
            if line.lower().startswith("content-type:"):
                header_lines[idx] = "Content-Type: application/json"
                break
        else:  # if not break
            header_lines.append("Content-Type: application/json")
    if isinstance(data, dict):
        for idx, line in enumerate(header_lines):
            if line.lower().startswith("content-type:"):
                header_lines[idx] = "Content-Type: application/x-www-form-urlencoded"
                break
        else:  # if not break
            header_lines.append("Content-Type: application/x-www-form-urlencoded")
    c.setopt(CurlOpt.HTTPHEADER, [h.encode() for h in header_lines])

    # cookies
    if isinstance(cookies, dict):
        cookies_str = "; ".join([f"{k}={v}" for k, v in cookies.items()])
    elif isinstance(cookies, SimpleCookie):
        cookies_str = "; ".join([f"{k}={v.value}" for k, v in cookies.items()])
    elif cookies is None:
        cookies_str = ""
    else:
        raise TypeError("cookies must be a dict or SimpleCookie")
    if cookies_str:
        c.setopt(CurlOpt.COOKIE, cookies_str.encode())

    # files
    if files:
        raise NotImplementedError("files")

    # auth
    if auth:
        username, password = auth
        c.setopt(CurlOpt.USERNAME, username.encode())
        c.setopt(CurlOpt.PASSWORD, password.encode())

    # timeout
    if isinstance(timeout, tuple):
        connect_timeout, read_timeout = timeout
        all_timeout = connect_timeout + read_timeout
        c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(connect_timeout * 1000))
        c.setopt(CurlOpt.TIMEOUT_MS, int(all_timeout * 1000))
    else:
        c.setopt(CurlOpt.TIMEOUT_MS, int(timeout * 1000))

    # allow_redirects
    c.setopt(CurlOpt.FOLLOWLOCATION, int(allow_redirects))

    # max_redirects
    c.setopt(CurlOpt.MAXREDIRS, max_redirects)

    # proxies
    if proxies is not None:
        if url.startswith("http://"):
            c.setopt(CurlOpt.PROXY, proxies["http"])
        elif url.startswith("https://"):
            c.setopt(CurlOpt.PROXY, proxies["https"])
            c.setopt(CurlOpt.HTTPPROXYTUNNEL, 1)

    # verify
    if not verify:
        c.setopt(CurlOpt.SSL_VERIFYPEER, 0)
        c.setopt(CurlOpt.SSL_VERIFYHOST, 0)

    # referer
    if referer:
        c.setopt(CurlOpt.REFERER, referer.encode())

    # accept_encoding
    if accept_encoding is not None:
        c.setopt(CurlOpt.ACCEPT_ENCODING, accept_encoding.encode())

    # impersonate
    if impersonate:
        if not BrowserType.has(impersonate):
            raise RequestsError(f"impersonate {impersonate} is not supported")
        c.impersonate(impersonate)

    buffer = BytesIO()
    c.setopt(CurlOpt.WRITEFUNCTION, buffer.write)
    header_buffer = BytesIO()
    c.setopt(CurlOpt.HEADERFUNCTION, header_buffer.write)

    try:
        c.perform()
    except CurlError as e:
        raise RequestsError(e)

    rsp = Response(c)
    rsp.url = cast(bytes, c.getinfo(CurlInfo.EFFECTIVE_URL)).decode()
    rsp.content = buffer.getvalue()
    rsp.status_code = cast(int, c.getinfo(CurlInfo.RESPONSE_CODE))
    rsp.ok = 200 <= rsp.status_code < 400
    header_lines = header_buffer.getvalue().splitlines()

    # TODO history urls
    header_list = []
    cookie_headers = []
    for header_line in header_lines:
        if not header_line.strip():
            continue
        if header_line.startswith(b"HTTP/"):
            # read header from last response
            rsp.reason = c.get_reason_phrase(header_line).decode()
            header_list = []  # empty header list for new redirected response
            continue
        name, value = header_line.split(b":", 1)
        value = value.lstrip()
        if name.lower() == b"set-cookie":
            cookie_headers.append(value)
        header_list.append((name, value))
    rsp.headers = Headers(header_list)

    rsp.cookies = SimpleCookie()
    for set_cookie_line in cookie_headers:
        print(set_cookie_line)
        rsp.cookies.load(set_cookie_line.decode())

    content_type = rsp.headers.get("Content-Type", default="")
    m = re.search(r"charset=([\w-]+)", content_type)
    charset = m.group(1) if m else "utf-8"

    rsp.charset = charset
    rsp.encoding = charset

    rsp.elapsed = cast(float, c.getinfo(CurlInfo.TOTAL_TIME))
    rsp.redirect_count = cast(int, c.getinfo(CurlInfo.REDIRECT_COUNT))
    rsp.redirect_url = cast(bytes, c.getinfo(CurlInfo.REDIRECT_URL)).decode()

    c.close()

    return rsp


head = partial(request, "HEAD")
get = partial(request, "GET")
post = partial(request, "POST")
put = partial(request, "PUT")
patch = partial(request, "PATCH")
delete = partial(request, "DELETE")
