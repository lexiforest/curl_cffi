import eventlet

eventlet.monkey_patch()

import threading  #  noqa: E402
import time  #  noqa: E402

from curl_cffi import requests  #  noqa: E402


def delay():
    requests.get("http://192.168.64.5:8080/delay/2", thread="eventlet")


def delay_not_working():
    requests.get("http://192.168.64.5:8080/delay/2")


def test_gevent_parallel(fn):
    start = time.time()
    threads = []
    for _ in range(6):
        t = threading.Thread(target=fn)
        threads.append(t)
        t.start()
    for t in threads:
        t.join()
    # if no thread, the time should be 12
    print(time.time() - start)
    # assert time.time() - start < 3


if __name__ == "__main__":
    test_gevent_parallel(delay_not_working)
    test_gevent_parallel(delay)
