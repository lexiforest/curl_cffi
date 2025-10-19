Benchmark
======

benchmark between curl_cffi and other python http clients

Sync clients
------

- curl_cffi
- requests
- pycurl
- [python-tls-client](https://github.com/FlorianREGAZ/Python-Tls-Client.git)
- httpx

Async clients
------

- curl_cffi
- httpx
- aiohttp

Async WebSocket
------

There are two benchmarks for the async WebSocket code:

1. [`client`](ws_bench_1_client.py)/[`server`](ws_bench_1_server.py) - Simple test for checking the speed of the `AsyncWebSocket` code. It just keeps sending the same chunk of bytes in a tight loop, the other end receives. This is unrealistic and CPU caching also skews the results. Just a sanity check to make sure things are working normally and there are no regressions.
2. [`benchmark`](benchmark/ws_bench_2.py) - Generates a large file full of random bytes and its hash. When ran as a server, it streams the file. The client connects and either downloads or uploads this file. The receiving end calculates and compares the file hash to make sure it matches the disk file.

> These do not factor in real internet conditions and run on loopback interfaces with really high MTU sizes

To run them you need Python 3.10+. In this directory, start by generating a self-signed cert:

```bash
openssl req -x509 -newkey rsa:2048 -nodes -keyout localhost.key -out localhost.crt -days 365 -subj "/CN=localhost"
```

Mark as executable:
```bash
chmod +x ws_bench_1_server.py ws_bench_1_client.py ws_bench_2.py
```

Install at least `aiohttp` and this code. Install `uvloop` or change the code to use the asyncio event loop. If you are on Windows, remove the `SSLContext` in the code and change WSS → WS URLs as needed.

By default, both benchmarks are configured to download `10GB` with a `65535` byte chunk size. You can [edit](ws_bench_1_server.py) the code to change these values as well as enabling upload. You can also enable concurrent upload/download, just uncomment the relevant code in the benchmark files.

> A concurrent test ends when the fastest side finishes first, which is usually the download side

These benchmarks can produce wildly varying results due to system level factors, CPU scheduling, etc.
To increase consistency, consider pinning the server and client to adjacent CPU cores:

```bash
taskset -c 0 ./ws_bench_1_server.py
taskset -c 1 ./ws_bench_1_client.py
```

> On a NUMA system (`lscpu | grep "NUMA node"`) with multiple CPUs, using `taskset` makes it consistent. If the benchmark server instance is running on one CPU and the client on another, it can result in reduced throughput due to crossing CPU socket boundaries.

### First Benchmark

Run the server:
```bash
./ws_bench_1_server.py
```

Run the client:
```bash
./ws_bench_1_client.py
```

### Second Benchmark

Generate the random bytes file (first time):
```bash
./ws_bench_2.py generate
```

Run the server:
```bash
./ws_bench_2.py server
```

Run the client:
```bash
./ws_bench_2.py client --test download
./ws_bench_2.py client --test upload
```

> Ensure sufficient disk space and RAM is available, the entire file will be received in RAM before being hashed

Target
------

All the clients run with session/client enabled.
