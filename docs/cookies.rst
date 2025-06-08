Cookies
=======

Save and load cookies
------

Do not use ``get_dict`` to dump and load cookies. Cookies are more than just plain
key-value pairs.

Using pickle:

.. code-block:: python

    # example from: https://github.com/encode/httpx/issues/895
    import pickle
    # import httpx
    import curl_cffi

    def save_cookies(client):
        with open("cookies.pk", "wb") as f:
            pickle.dump(client.cookies.jar._cookies, f)

    def load_cookies():
        if not os.path.isfile("cookies.pk"):
            return None
        with open("cookies.pk", "rb") as f:
            return pickle.load(f)

    # client = httpx.Client(cookies=load_cookies())
    client = curl_cffi.Session()
    client.get("https://httpbin.org/cookies/set/foo/bar")
    save_cookies(client)

    client = curl_cffi.Session()
    client.cookies.jar._cookies.update(load_cookies())
    print(client.cookies.get("foo"))


Using mozilla cookie jar:

See: https://github.com/lexiforest/curl_cffi/issues/381

TODO: expose libcurl's native cookies.txt support.


Discard cookies when using Session
----------------------------------

You may need to discard cookies when using sessions, especially when using ``AsyncSession``.

Use the ``discard_cookies`` option.


.. code-block:: python

    s = requests.Session()

    set_url = "https://httpbin.org/cookies"

    r = s.get(set_url)
    assert r.cookies["foo"] == s.cookies["foo"]
    old_cookie = r.cookies["foo"]

    # Let's start discarding cookies
    s.discard_cookies = True
    r = s.get(set_url)
    assert r.cookies["foo"] != s.cookies["foo"]
    assert old_cookie == s.cookies["foo"]

    # The behavior can be reverted
    s.discard_cookies = False
    r = s.get(set_url)
    assert r.cookies["foo"] == s.cookies["foo"]
    old_cookie = r.cookies["foo"]

    # Also works as request parameter
    r = s.get(set_url, discard_cookies=True)
    assert r.cookies["foo"] != s.cookies["foo"]
    assert old_cookie == s.cookies["foo"]
