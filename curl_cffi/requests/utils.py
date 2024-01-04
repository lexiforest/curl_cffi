from __future__ import annotations

from io import BytesIO
from json import dumps
from typing import Callable, Dict, List, Any, Optional, Tuple, Union, TYPE_CHECKING
from urllib.parse import ParseResult, parse_qsl, unquote, urlencode, urlparse
import warnings

from .. import CurlOpt
from ..curl import CURL_WRITEFUNC_ERROR
from .cookies import Cookies, CookieTypes
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .models import BrowserType, Request

if TYPE_CHECKING:
    from ..const import CurlHttpVersion
    from .cookies import CookieTypes
    from .headers import HeaderTypes
    from .session import ProxySpec

not_set: Any = object()


def _update_url_params(url: str, params: dict) -> str:
    """Add GET params to provided URL being aware of existing.

    Parameters:
        url: string of target URL
        params: dict containing requested params to be added

    Returns:
        string with updated URL

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
    parsed_get_args.update({k: dumps(v) for k, v in parsed_get_args.items() if isinstance(v, (bool, dict))})

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


def _update_header_line(header_lines: List[str], key: str, value: str):
    """Update header line list by key value pair."""
    for idx, line in enumerate(header_lines):
        if line.lower().startswith(key.lower() + ":"):
            header_lines[idx] = f"{key}: {value}"
            break
    else:  # if not break
        header_lines.append(f"{key}: {value}")


def _set_curl_options(
    curl,
    method: str,
    url: str,
    *,
    params: Optional[dict] = None,
    data: Optional[Union[Dict[str, str], str, BytesIO, bytes]] = None,
    json: Optional[dict] = None,
    headers: Optional[HeaderTypes] = None,
    session_cookies: Optional[Cookies] = None,
    cookies: Optional[CookieTypes] = None,
    files: Optional[Dict] = None,
    auth: Optional[Tuple[str, str]] = None,
    timeout: Optional[Union[float, Tuple[float, float], object]] = not_set,
    allow_redirects: bool = True,
    max_redirects: int = -1,
    proxies: Optional[ProxySpec] = None,
    proxy_auth: Optional[Tuple[str, str]] = None,
    session_verify: Union[bool, str] = True,
    verify: Optional[Union[bool, str]] = None,
    referer: Optional[str] = None,
    accept_encoding: Optional[str] = "gzip, deflate, br",
    content_callback: Optional[Callable] = None,
    impersonate: Optional[Union[str, BrowserType]] = None,
    default_headers: bool = True,
    http_version: Optional[CurlHttpVersion] = None,
    interface: Optional[str] = None,
    stream: bool = False,
    max_recv_speed: int = 0,
    queue_class: Any = None,
    event_class: Any = None,
    curl_options: Optional[dict] = None,
):
    c = curl

    # method
    if method == "POST":
        c.setopt(CurlOpt.POST, 1)
    elif method != "GET":
        c.setopt(CurlOpt.CUSTOMREQUEST, method.encode())

    # url
    if params:
        url = _update_url_params(url, params)
    c.setopt(CurlOpt.URL, url.encode())

    # data/body/json
    if isinstance(data, dict):
        body = urlencode(data).encode()
    elif isinstance(data, str):
        body = data.encode()
    elif isinstance(data, BytesIO):
        body = data.read()
    elif isinstance(data, bytes):
        body = data
    elif data is None:
        body = b""
    else:
        raise TypeError("data must be dict, str, BytesIO or bytes")
    if json is not None:
        body = dumps(json, separators=(",", ":")).encode()

    # Tell libcurl to be aware of bodies and related headers when,
    # 1. POST/PUT/PATCH, even if the body is empty, it's up to curl to decide what to do;
    # 2. GET/DELETE with body, although it's against the RFC, some applications. e.g. Elasticsearch, use this.
    if body or method in ("POST", "PUT", "PATCH"):
        c.setopt(CurlOpt.POSTFIELDS, body)
        # necessary if body contains '\0'
        c.setopt(CurlOpt.POSTFIELDSIZE, len(body))

    # headers
    h = Headers(headers)

    # remove Host header if it's unnecessary, otherwise curl maybe confused.
    # Host header will be automatically added by curl if it's not present.
    # https://github.com/yifeikong/curl_cffi/issues/119
    host_header = h.get("Host")
    if host_header is not None:
        u = urlparse(url)
        if host_header == u.netloc or host_header == u.hostname:
            try:
                del h["Host"]
            except KeyError:
                pass

    header_lines = []
    for k, v in h.multi_items():
        header_lines.append(f"{k}: {v}")
    if json is not None:
        _update_header_line(header_lines, "Content-Type", "application/json")
    if isinstance(data, dict) and method != "POST":
        _update_header_line(header_lines, "Content-Type", "application/x-www-form-urlencoded")
    # print("header lines", header_lines)
    c.setopt(CurlOpt.HTTPHEADER, [h.encode() for h in header_lines])

    req = Request(url, h, method)

    # cookies
    c.setopt(CurlOpt.COOKIEFILE, b"")  # always enable the curl cookie engine first
    c.setopt(CurlOpt.COOKIELIST, "ALL")  # remove all the old cookies first.

    if session_cookies:
        for morsel in session_cookies.get_cookies_for_curl(req):
            # print("Setting", morsel.to_curl_format())
            curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())
    if cookies:
        temp_cookies = Cookies(cookies)
        for morsel in temp_cookies.get_cookies_for_curl(req):
            curl.setopt(CurlOpt.COOKIELIST, morsel.to_curl_format())

    # files
    if files:
        raise NotImplementedError("Files has not been implemented.")

    # auth
    if auth:
        username, password = auth
        c.setopt(CurlOpt.USERNAME, username.encode())  # type: ignore
        c.setopt(CurlOpt.PASSWORD, password.encode())  # type: ignore

    # timeout
    if timeout is None:
        timeout = 0  # indefinitely

    if isinstance(timeout, tuple):
        connect_timeout, read_timeout = timeout
        all_timeout = connect_timeout + read_timeout
        c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(connect_timeout * 1000))
        if not stream:
            c.setopt(CurlOpt.TIMEOUT_MS, int(all_timeout * 1000))
    else:
        if not stream:
            c.setopt(CurlOpt.TIMEOUT_MS, int(timeout * 1000))  # type: ignore
        else:
            c.setopt(CurlOpt.CONNECTTIMEOUT_MS, int(timeout * 1000))  # type: ignore

    # allow_redirects
    c.setopt(CurlOpt.FOLLOWLOCATION, int(allow_redirects))

    # max_redirects
    c.setopt(CurlOpt.MAXREDIRS, max_redirects)

    # proxies
    if proxies:
        parts = urlparse(url)
        proxy = proxies.get(parts.scheme, proxies.get("all"))
        if parts.hostname:
            proxy = (
                proxies.get(
                    f"{parts.scheme}://{parts.hostname}",
                    proxies.get(f"all://{parts.hostname}"),
                )
                or proxy
            )

        if proxy is not None:
            if parts.scheme == "https" and proxy.startswith("https://"):
                warnings.warn(
                    "You may be using http proxy WRONG, the prefix should be 'http://' not 'https://',"
                    "see: https://github.com/yifeikong/curl_cffi/issues/6",
                    RuntimeWarning,
                    stacklevel=2,
                )

            c.setopt(CurlOpt.PROXY, proxy)
            # for http proxy, need to tell curl to enable tunneling
            if not proxy.startswith("socks"):
                c.setopt(CurlOpt.HTTPPROXYTUNNEL, 1)

            # proxy_auth
            if proxy_auth:
                username, password = proxy_auth
                c.setopt(CurlOpt.PROXYUSERNAME, username.encode())
                c.setopt(CurlOpt.PROXYPASSWORD, password.encode())

    # verify
    if verify is False or not session_verify and verify is None:
        c.setopt(CurlOpt.SSL_VERIFYPEER, 0)
        c.setopt(CurlOpt.SSL_VERIFYHOST, 0)

    # cert for this single request
    if isinstance(verify, str):
        c.setopt(CurlOpt.CAINFO, verify)

    # cert for the session
    if verify in (None, True) and isinstance(session_verify, str):
        c.setopt(CurlOpt.CAINFO, session_verify)

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
        c.impersonate(impersonate, default_headers=default_headers)

    # http_version, after impersonate, which will change this to http2
    if http_version:
        c.setopt(CurlOpt.HTTP_VERSION, http_version)

    # set extra curl options, must come after impersonate, because it will alter some options
    if curl_options:
        for k, v in curl_options.items():
            c.setopt(k, v)

    buffer = None
    q = None
    header_recved = None
    quit_now = None
    if stream:
        q = queue_class()  # type: ignore
        header_recved = event_class()
        quit_now = event_class()

        def qput(chunk):
            if not header_recved.is_set():
                header_recved.set()
            if quit_now.is_set():
                return CURL_WRITEFUNC_ERROR
            q.put_nowait(chunk)
            return len(chunk)

        c.setopt(CurlOpt.WRITEFUNCTION, qput)  # type: ignore
    elif content_callback is not None:
        c.setopt(CurlOpt.WRITEFUNCTION, content_callback)
    else:
        buffer = BytesIO()
        c.setopt(CurlOpt.WRITEDATA, buffer)
    header_buffer = BytesIO()
    c.setopt(CurlOpt.HEADERDATA, header_buffer)

    if method == "HEAD":
        c.setopt(CurlOpt.NOBODY, 1)

    # interface
    if interface:
        c.setopt(CurlOpt.INTERFACE, interface.encode())

    # max_recv_speed
    # do not check, since 0 is a valid value to disable it
    c.setopt(CurlOpt.MAX_RECV_SPEED_LARGE, max_recv_speed)

    return req, buffer, header_buffer, q, header_recved, quit_now
