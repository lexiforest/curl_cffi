Cookies
=======

How to save and load cookies
------

Do not use ``get_dict`` to dump and load cookies. Cookies are more than just plain
key-value pairs.

Using pickle:

.. code-block:: python

    # example from: https://github.com/encode/httpx/issues/895
    import pickle
    # import httpx
    from curl_cffi import requests

    def save_cookies(client):
        with open("cookies.pk", "wb") as f:
            pickle.dump(client.cookies.jar._cookies, f)

    def load_cookies():
        if not os.path.isfile("cookies.pk"):
            return None
        with open("cookies.pk", "rb") as f:
            return pickle.load(f)

    # client = httpx.Client(cookies=load_cookies())
    client = requests.Session()
    client.get("https://httpbin.org/cookies/set/foo/bar")
    save_cookies(client)

    client = requests.Session()
    client.cookies.jar._cookies.update(load_cookies())
    print(client.cookies.get("foo"))


Using mozilla cookie jar:

See: https://github.com/lexiforest/curl_cffi/issues/381

TODO: expose libcurl's native cookies.txt support.
