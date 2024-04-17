import asyncio
import queue
import threading
import time
from io import BytesIO

import aiohttp
import httpx
import pandas as pd
import pycurl
import requests
import tls_client

import curl_cffi
import curl_cffi.requests

# import uvloop
# uvloop.install()

results = []


class FakePycurlSession:
    def __init__(self):
        self.c = pycurl.Curl()

    def get(self, url):
        buffer = BytesIO()
        self.c.setopt(pycurl.URL, url)
        self.c.setopt(pycurl.WRITEDATA, buffer)
        self.c.perform()

    def __del__(self):
        self.c.close()


class FakeCurlCffiSession:
    def __init__(self):
        self.c = curl_cffi.Curl()

    def get(self, url):
        buffer = BytesIO()
        self.c.setopt(curl_cffi.CurlOpt.URL, url)
        self.c.setopt(curl_cffi.CurlOpt.WRITEDATA, buffer)
        self.c.perform()

    def __del__(self):
        self.c.close()


for size in ["1k", "20k", "200k"]:
    stats = {}
    url = "http://localhost:8000/" + size

    for name, SessionClass in [
        ("requests", requests.Session),
        ("httpx_sync", httpx.Client),
        ("tls_client", tls_client.Session),
        ("curl_cffi_sync", curl_cffi.requests.Session),
        ("curl_cffi_raw", FakeCurlCffiSession),
        ("pycurl", FakePycurlSession),
    ]:
        s = SessionClass()
        start = time.time()
        for _ in range(1000):
            s.get(url)
        dur = time.time() - start
        stats[name] = dur
        results.append({"name": name, "size": size, "duration": dur})

    print(f"One worker, {size}: {stats}")

df = pd.DataFrame(results)
df.to_csv("single_worker.csv", index=False, float_format="%.4f")

results = []


def worker(q, done, SessionClass):
    s = SessionClass()
    while not done.is_set():
        try:
            url = q.get_nowait()
        except Exception:
            continue
        s.get(url)
        q.task_done()


async def aiohttp_worker(q, done, s):
    while not done.is_set():
        url = await q.get()
        async with s.get(url) as response:
            await response.read()
        q.task_done()


async def httpx_worker(q, done, s):
    while not done.is_set():
        url = await q.get()
        await s.get(url)
        q.task_done()


for size in ["1k", "20k", "200k"]:
    url = "http://localhost:8000/" + size
    stats = {}
    for name, SessionClass in [
        ("requests", requests.Session),
        ("httpx_sync", httpx.Client),
        ("tls_client", tls_client.Session),
        ("curl_cffi_sync", curl_cffi.requests.Session),
        ("curl_cffi_raw", FakeCurlCffiSession),
        ("pycurl", FakePycurlSession),
    ]:
        q = queue.Queue()
        for _ in range(1000):
            q.put(url)
        done = threading.Event()
        start = time.time()
        threads = []
        for _ in range(10):
            t = threading.Thread(target=worker, args=(q, done, SessionClass))
            threads.append(t)
            t.start()
        q.join()
        done.set()
        dur = time.time() - start
        stats[name] = dur
        results.append({"name": name, "size": size, "duration": dur})
        for t in threads:
            t.join()
    # print(stats)

    async def test_asyncs_workers(url, size, stats):
        for name, worker, SessionClass in [
            ("aiohttp", aiohttp_worker, aiohttp.ClientSession),
            ("httpx_async", httpx_worker, httpx.AsyncClient),
            ("curl_cffi_async", httpx_worker, curl_cffi.requests.AsyncSession),
        ]:
            q = asyncio.Queue()
            for _ in range(1000):
                await q.put(url)
            done = asyncio.Event()
            start = time.time()
            workers = []
            async with SessionClass() as s:
                for _ in range(10):
                    w = asyncio.create_task(worker(q, done, s))
                    workers.append(w)
                await q.join()
                done.set()
            dur = time.time() - start
            stats[name] = dur
            results.append({"name": name, "size": size, "duration": dur})
            for w in workers:
                w.cancel()

    asyncio.run(test_asyncs_workers(url, size, stats))
    print(f"10 Workers, {size}: {stats}")

df = pd.DataFrame(results)
df.to_csv("multiple_workers.csv", index=False, float_format="%.4f")
