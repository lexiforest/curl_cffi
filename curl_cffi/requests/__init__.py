from functools import partial
from io import BytesIO
from typing import Dict, Optional, Tuple, Union

from .cookies import Cookies, CookieTypes, Response
from .errors import RequestsError
from .headers import Headers, HeaderTypes
from .session import BrowserType, Session


def request(
    method: str,
    url: str,
    params: Optional[dict] = None,
    data: Optional[Union[Dict[str, str], BytesIO, bytes]] = None,
    json: Optional[dict] = None,
    headers: Optional[HeaderTypes] = None,
    cookies: Optional[CookieTypes] = None,
    files: Optional[Dict] = None,
    auth: Optional[Tuple[str, str]] = None,
    timeout: Union[float, Tuple[float, float]] = 30,
    allow_redirects: bool = True,
    max_redirects: int = -1,
    proxies: Optional[dict] = None,
    verify: Optional[bool] = None,
    referer: Optional[str] = None,
    accept_encoding: Optional[str] = "gzip, deflate, br",
    impersonate: Optional[Union[str, BrowserType]] = None,
) -> Response:
    with Session() as s:
        return s.request(
            method,
            url,
            params,
            data,
            json,
            headers,
            cookies,
            files,
            auth,
            timeout,
            allow_redirects,
            max_redirects,
            proxies,
            verify,
            referer,
            accept_encoding,
            impersonate,
        )


head = partial(request, "HEAD")
get = partial(request, "GET")
post = partial(request, "POST")
put = partial(request, "PUT")
patch = partial(request, "PATCH")
delete = partial(request, "DELETE")
