import asyncio
import contextlib
import json
import os
import threading
import time
import typing
from asyncio import sleep
from collections import defaultdict
from urllib.parse import parse_qs

import proxy
import pytest
import trustme
import uvicorn
import websockets
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import (
    BestAvailableEncryption,
    Encoding,
    PrivateFormat,
    load_pem_private_key,
)
from fastapi import FastAPI, Form, UploadFile
from httpx import URL
from uvicorn.config import Config
from uvicorn.main import Server

ENVIRONMENT_VARIABLES = {
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "SSLKEYLOGFILE",
}


@pytest.fixture(
    params=[
        pytest.param("asyncio", marks=pytest.mark.asyncio),
        pytest.param("trio", marks=pytest.mark.trio),
    ]
)
def async_environment(request: typing.Any) -> str:
    """
    Mark a test function to be run on both asyncio and trio.
    Equivalent to having a pair of tests, each respectively marked with
    '@pytest.mark.asyncio' and '@pytest.mark.trio'.
    Intended usage:
    ```
    @pytest.mark.usefixtures("async_environment")
    async def my_async_test():
        ...
    ```
    """
    return request.param


@pytest.fixture(scope="function", autouse=True)
def clean_environ():
    """Keeps os.environ clean for every test without having to mock os.environ"""
    original_environ = os.environ.copy()
    os.environ.clear()
    os.environ.update(
        {
            k: v
            for k, v in original_environ.items()
            if k not in ENVIRONMENT_VARIABLES and k.lower() not in ENVIRONMENT_VARIABLES
        }
    )
    yield
    os.environ.clear()
    os.environ.update(original_environ)


async def app(scope, receive, send):
    assert scope["type"] == "http"
    print("scope_path:", scope["path"])
    if scope["path"].startswith("/slow_response"):
        await slow_response(scope, receive, send)
    elif scope["path"].startswith("/status"):
        await status_code(scope, receive, send)
    elif scope["path"].startswith("/echo_path"):
        await echo_path(scope, receive, send)
    elif scope["path"].startswith("/echo_params"):
        await echo_params(scope, receive, send)
    elif scope["path"].startswith("/stream"):
        await stream(scope, receive, send)
    elif scope["path"].startswith("/large"):
        await large(scope, receive, send)
    elif scope["path"].startswith("/empty_body"):
        await empty_body(scope, receive, send)
    elif scope["path"].startswith("/echo_body"):
        await echo_body(scope, receive, send)
    elif scope["path"].startswith("/echo_binary"):
        await echo_binary(scope, receive, send)
    elif scope["path"].startswith("/echo_headers"):
        await echo_headers(scope, receive, send)
    elif scope["path"].startswith("/echo_cookies"):
        await echo_cookies(scope, receive, send)
    elif scope["path"].startswith("/set_headers"):
        await set_headers(scope, receive, send)
    elif scope["path"].startswith("/set_cookies"):
        await set_cookies(scope, receive, send)
    elif scope["path"].startswith("/delete_cookies"):
        await delete_cookies(scope, receive, send)
    elif scope["path"].startswith("/set_special_cookies"):
        await set_special_cookies(scope, receive, send)
    elif scope["path"].startswith("/redirect_301"):
        await redirect_301(scope, receive, send)
    elif scope["path"].startswith("/redirect_to"):
        await redirect_to(scope, receive, send)
    elif scope["path"].startswith("/redirect_loop"):
        await redirect_loop(scope, receive, send)
    elif scope["path"].startswith("/redirect_then_echo_cookies"):
        await redirect_then_echo_cookies(scope, receive, send)
    elif scope["path"].startswith("/redirect_then_echo_headers"):
        await redirect_then_echo_headers(scope, receive, send)
    elif scope["path"].startswith("/json"):
        await hello_world_json(scope, receive, send)
    elif scope["path"].startswith("/incomplete_read"):
        await incomplete_read(scope, receive, send)
    elif scope["path"].startswith("/gbk"):
        await hello_world_gbk(scope, receive, send)
    elif scope["path"].startswith("/windows1251"):
        await hello_world_windows1251(scope, receive, send)
    elif scope["path"].startswith("http://"):
        await http_proxy(scope, receive, send)
    elif scope["method"] == "CONNECT":
        await https_proxy(scope, receive, send)
    else:
        await hello_world(scope, receive, send)


async def hello_world(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain; charset=utf-8"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def hello_world_json(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": b'{"Hello": "world!"}'})


async def hello_world_gbk(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain; charset=gbk"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def hello_world_windows1251(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": "Bсеки човек има право на образование.".encode("cp1251"),
        }
    )


async def http_proxy(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": b'{"Hello": "http_proxy!"}'})


async def https_proxy(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": b'{"Hello": "https_proxy!"}'})


async def slow_response(scope, receive, send):
    await sleep(0.2)
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def status_code(scope, receive, send):
    status_code = int(scope["path"].replace("/status/", ""))
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def echo_body(scope, receive, send):
    body = b""
    more_body = True

    while more_body:
        message = await receive()
        body += message.get("body", b"")
        more_body = message.get("more_body", False)

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    # print("server: received:", body)
    await send({"type": "http.response.body", "body": body})


async def echo_path(scope, receive, send):
    body = {"path": scope["path"], "method": scope["method"]}
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": json.dumps(body).encode()})


async def echo_params(scope, receive, send):
    body = {"params": parse_qs(scope["query_string"].decode(), keep_blank_values=True)}
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": json.dumps(body).encode()})


async def stream(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    body = {"path": scope["path"], "params": parse_qs(scope["query_string"].decode())}
    n = int(parse_qs(scope["query_string"].decode()).get("n", [10])[0])
    for _ in range(n - 1):
        await send(
            {
                "type": "http.response.body",
                "body": json.dumps(body).encode() + b"\n",
                "more_body": True,
            }
        )
    await send(
        {
            "type": "http.response.body",
            "body": json.dumps(body).encode(),
            "more_body": False,
        }
    )


async def large(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": os.urandom(20 * 1024 * 1024),  # 20MiB
            "more_body": False,
        }
    )


async def empty_body(scope, receive, send):
    await send({"type": "http.response.start", "status": 200})
    await send({"type": "http.response.body", "body": b""})


async def echo_binary(scope, receive, send):
    body = b""
    more_body = True

    while more_body:
        message = await receive()
        body += message.get("body", b"")
        more_body = message.get("more_body", False)

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/octet-stream"]],
        }
    )
    await send({"type": "http.response.body", "body": body})


async def echo_headers(scope, receive, send):
    body = defaultdict(list)
    # print(scope.get("headers"))
    for name, value in scope.get("headers", []):
        body[name.capitalize().decode()].append(value.decode())

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": json.dumps(body).encode()})


async def echo_cookies(scope, receive, send):
    headers = scope.get("headers", [])
    cookies = {}
    for header in headers:
        if header[0].decode() == "cookie":
            cookies_header = header[1].decode()
            for cookie in cookies_header.split(";"):
                name, value = cookie.strip().split("=")
                cookies[name] = value
            break
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"application/json"]],
        }
    )
    await send({"type": "http.response.body", "body": json.dumps(cookies).encode()})


async def set_headers(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"x-test", b"test"],
                [b"x-test", b"test2"],
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def set_cookies(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"set-cookie", b"foo=bar"],
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def delete_cookies(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"set-cookie", b"foo=; Max-Age=0"],
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def set_special_cookies(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/plain"],
                [b"set-cookie", b"foo=bar space"],
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello, world!"})


async def redirect_301(scope, receive, send):
    await send({"type": "http.response.start", "status": 301, "headers": [[b"location", b"/"]]})
    await send({"type": "http.response.body", "body": b"Redirecting..."})


async def redirect_to(scope, receive, send):
    params = parse_qs(scope["query_string"].decode())
    await send(
        {
            "type": "http.response.start",
            "status": 301,
            "headers": [[b"location", params["to"][0].encode()]],
        }
    )
    await send({"type": "http.response.body", "body": b"Redirecting..."})


async def redirect_loop(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 301,
            "headers": [[b"location", b"/redirect_loop"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Redirecting..."})


async def redirect_then_echo_cookies(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 301,
            "headers": [[b"location", b"/echo_cookies"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Redirecting..."})


async def redirect_then_echo_headers(scope, receive, send):
    # for name, value in scope.get("headers", []):
    #     print("Header>>>", name, ":", value)
    await send(
        {
            "type": "http.response.start",
            "status": 301,
            "headers": [[b"location", b"/echo_headers"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Redirecting..."})


async def incomplete_read(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                [b"content-type", b"text/html; charset=utf-8"],
                [b"content-length", b"234234"],
            ],
        }
    )
    await send({"type": "http.response.body", "body": b"<html></html>"})


@pytest.fixture(scope="session")
def cert_authority():
    return trustme.CA()


@pytest.fixture(scope="session")
def ca_cert_pem_file(cert_authority):
    with cert_authority.cert_pem.tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def localhost_cert(cert_authority):
    return cert_authority.issue_cert("localhost")


@pytest.fixture(scope="session")
def cert_pem_file(localhost_cert):
    with localhost_cert.cert_chain_pems[0].tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def cert_private_key_file(localhost_cert):
    with localhost_cert.private_key_pem.tempfile() as tmp:
        yield tmp


@pytest.fixture(scope="session")
def cert_encrypted_private_key_file(localhost_cert):
    # Deserialize the private key and then reserialize with a password
    private_key = load_pem_private_key(
        localhost_cert.private_key_pem.bytes(), password=None, backend=default_backend()
    )
    encrypted_private_key_pem = trustme.Blob(
        private_key.private_bytes(
            Encoding.PEM,
            PrivateFormat.TraditionalOpenSSL,
            BestAvailableEncryption(password=b"password"),
        )
    )
    with encrypted_private_key_pem.tempfile() as tmp:
        yield tmp


class TestServer(Server):
    @property
    def url(self) -> URL:
        protocol = "https" if self.config.is_ssl else "http"
        return URL(f"{protocol}://{self.config.host}:{self.config.port}/")

    def install_signal_handlers(self) -> None:
        # Disable the default installation of handlers for signals such as SIGTERM,
        # because it can only be done in the main thread.
        pass

    async def serve(self, sockets=None):
        self.restart_requested = asyncio.Event()

        loop = asyncio.get_event_loop()
        tasks = {
            loop.create_task(super().serve(sockets=sockets)),
            loop.create_task(self.watch_restarts()),
        }
        await asyncio.wait(tasks)

    async def restart(self) -> None:  # pragma: nocover
        # This coroutine may be called from a different thread than the one the
        # server is running on, and from an async environment that's not asyncio.
        # For this reason, we use an event to coordinate with the server
        # instead of calling shutdown()/startup() directly, and should not make
        # any asyncio-specific operations.
        self.started = False
        self.restart_requested.set()
        while not self.started:
            await sleep(0.2)

    async def watch_restarts(self):  # pragma: nocover
        while True:
            if self.should_exit:
                return

            try:
                await asyncio.wait_for(self.restart_requested.wait(), timeout=0.1)
            except asyncio.TimeoutError:
                continue

            self.restart_requested.clear()
            await self.shutdown()
            await self.startup()


async def echo(websocket):
    while True:
        name = await websocket.recv()
        if isinstance(name, bytes):
            name = name.decode()
        # print(f"<<< {name}")

        await websocket.send(name)
        # print(f">>> {name}")


class TestWebsocketServer:
    def __init__(self, port):
        self.url = f"ws://127.0.0.1:{port}"
        self.port = port

    def run(self):
        async def serve(port):
            # GitHub actions only likes 127, not localhost, wtf...
            async with websockets.serve(echo, "127.0.0.1", port):  # pyright: ignore
                await asyncio.Future()  # run forever

        asyncio.run(serve(self.port))


def serve_in_thread(server: Server):
    thread = threading.Thread(target=server.run)
    thread.start()
    try:
        while not server.started:
            time.sleep(1e-3)
        yield server
    finally:
        server.should_exit = True
        thread.join()


@pytest.fixture(scope="session")
def ws_server():
    server = TestWebsocketServer(port=8964)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        time.sleep(2)  # FIXME find a reliable way to check the server is up
        yield server
    finally:
        pass
        # thread.join()


@pytest.fixture(scope="session")
def server():
    config = Config(app=app, lifespan="off", loop="asyncio")
    server = TestServer(config=config)
    yield from serve_in_thread(server)


@pytest.fixture(scope="session")
def https_server(cert_pem_file, cert_private_key_file):
    config = Config(
        app=app,
        lifespan="off",
        ssl_certfile=cert_pem_file,
        ssl_keyfile=cert_private_key_file,
        port=8001,
        loop="asyncio",
    )
    server = TestServer(config=config)
    yield from serve_in_thread(server)


@pytest.fixture(scope="session")
def proxy_server(request):
    ps = proxy.Proxy(port=8002, plugins=["proxy.plugin.ManInTheMiddlePlugin"])
    request.addfinalizer(ps.__exit__)
    return ps.__enter__()


class FileServer(uvicorn.Server):
    def install_signal_handlers(self):
        pass

    @contextlib.contextmanager
    def run_in_thread(self):
        thread = threading.Thread(target=self.run)
        thread.start()
        try:
            while not self.started:
                time.sleep(1e-3)
            yield
        finally:
            self.should_exit = True
            thread.join()

    @property
    def url(self):
        return f"http://{self.config.host}:{self.config.port}"


file_app = FastAPI()


@file_app.post("/file")
def upload_single_file(image: UploadFile, foo: typing.Optional[str] = Form(None)):
    content = image.file.read()
    return {
        "foo": foo,
        "filename": image.filename,
        "content_type": image.content_type,
        "size": len(content),
    }


@file_app.post("/files")
def upload_multi_files(images: typing.List[UploadFile]):
    files = []
    for image in images:
        content = image.file.read()
        files.append(
            {
                "filename": image.filename,
                "content_type": image.content_type,
                "size": len(content),
            }
        )

    return {"files": files}


@file_app.post("/two-files")
def upload_two_files(image1: UploadFile, image2: UploadFile):
    return {
        "size1": len(image1.file.read()),
        "size2": len(image2.file.read()),
    }


@pytest.fixture(scope="session")
def file_server():
    FastAPI()
    config = uvicorn.Config(file_app, host="127.0.0.1", port=2952, log_level="info")
    server = FileServer(config=config)
    with server.run_in_thread():
        yield server
