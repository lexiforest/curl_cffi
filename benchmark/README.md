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

Target
------

All the clients run with session/client enabled.

Async WebSocket
------

Two distinct benchmarks are provided to evaluate the performance of the `AsyncWebSocket` implementation under different conditions.

1. Simple Throughput Test ([`client`](ws_bench_1_client.py), [`server`](ws_bench_1_server.py))

    This is a lightweight, in-memory benchmark designed to measure the raw throughput and overhead of the WebSocket client. The server sends a repeating chunk of random bytes from memory, and the client receives it. This test is useful for quick sanity checks and detecting performance regressions under ideal, CPU-cached conditions.

2. Verified Streaming Test ([`code`](ws_bench_2.py))

    This is a rigorous, end-to-end test. It first generates a multi-gigabyte file of random data and its SHA256 hash. The benchmark then streams this file from disk over the WebSocket connection. The receiving end calculates the hash of the incoming stream and verifies it against the original, ensuring complete data integrity.

    It measures the performance of the entire system pipeline, including Disk I/O speed, CPU hashing speed, and network transfer. On many systems, it is likely to be bottlenecked by the CPU's hashing performance or the disk speed. The result of the first run should be discarded as this reflects disk read speed rather than code performance, when the file is not cached in RAM.

Prerequisites
------

- Python 3.10+
- Pip packages

```bash
pip install aiohttp curl_cffi
```

> `uvloop` is highly recommended for performance on Linux and macOS. The benchmarks will automatically fall back to the standard asyncio event loop if it is not installed or on Windows.

Setup
------

1. TLS certificate (optional)

    These benchmarks are configured to use WSS (secure WebSockets) by default on Linux and macOS. To generate a self-signed certificate:

    ```bash
    openssl req -x509 -newkey rsa:2048 -nodes -keyout localhost.key -out localhost.crt -days 365 -subj "/CN=localhost"
    ```

    > **Note**: If you are on any platform and skip certificate generation, the benchmarks will use the insecure `ws://` instead.

2. Configuration

    The benchmark parameters (total data size, chunk size) can be modified by editing the [`TestConfig`](ws_bench_utils.py#L76) class. By default, both benchmarks are configured for `10 GiB` of data transfer.

WebSocket Benchmarks
------

It is recommended to run the server and client in different terminal windows.

Benchmark 1: Simple Throughput Test
------

1. Start the Server:

    ```bash
    python ws_bench_1_server.py
    ```

2. Run the Client:

    ```bash
    python ws_bench_1_client.py
    ```

Benchmark 2: Verified Streaming Test
------

1. Generate Test File (Initial Setup):

    This command will create a large (`10 GiB`) file named `testdata.bin` and its hash:

    ```bash
    python ws_bench_2.py generate
    ```

    > Ensure you have sufficient disk space available

2. Start the Server:

    ```bash
    python ws_bench_2.py server
    ```

3. Run the Client (Choose one):

    > This benchmark requires enough available RAM **equal to the size of the random data** (e.g. `10 GiB`).

    - To test download speed (server sends, client receives):

    ```bash
    python ws_bench_2.py client --test download
    ```

    - To test upload speed (client sends, server receives):

    ```bash
    python ws_bench_2.py client --test upload
    ```

Performance Considerations
------

Benchmark results can vary significantly based on system-level factors. The following should be kept in mind:

- **Loopback Interface**: These tests run on the loopback interface (`127.0.0.1`), which does not represent real-world internet conditions (latency, packet loss, etc.).

- **CPU Affinity**: For maximum consistency, especially on multi-core or multi-CPU (NUMA) systems, you can pin the server and client processes to specific CPU cores. This avoids performance penalties from processes migrating between cores or crossing CPU socket boundaries.

    **On Linux:**
    Use `taskset` to specify a CPU core (e.g., core 0 for the server, core 1 for the client).

    ```bash
    # Terminal 1
    taskset -c 0 python ws_bench_1_server.py

    # Terminal 2
    taskset -c 1 python ws_bench_1_client.py
    ```

    **On Windows:**
    Use the `start /affinity` command. The affinity mask is a hexadecimal number (`1` for CPU 0, `2` for CPU 1, `4` for CPU 2, etc.).

    ```powershell
    # PowerShell/CMD 1
    start /affinity 1 python ws_bench_1_server.py

    # PowerShell/CMD 2
    start /affinity 2 python ws_bench_1_client.py
    ```

- **Concurrent Tests**: The [`ws_bench_1_client.py`](ws_bench_1_client.py) benchmark mode can be changed to download/upload/concurrent by changing the [`BenchmarkDirection`](ws_bench_utils.py#L100) enum. A concurrent test completes when both directions finish.

- **Queue Sizes**: Adjust the [`send_queue`](ws_bench_utils.py#L90) and [`recv_queue`](ws_bench_utils.py#L89) sizes within the [`TestConfig`](ws_bench_utils.py#L76) class to observe the impact on performance and backpressure.
