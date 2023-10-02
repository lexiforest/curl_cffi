from curl_cffi import requests

with requests.Session() as s:
    w = s.connect("ws://localhost:8765")
    w.send(b"Foo")
    reply = w.recv()
    assert reply == b"Hello Foo!"
