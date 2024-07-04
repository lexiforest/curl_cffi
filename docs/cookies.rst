Cookies
=======

How to save and load cookies
------

Do not use ``get_dict`` to dump and load cookies. Cookies are more than just plain
key-value pairs.

.. code-block:: python

    import pickle
    # import httpx
    from curl_cffi import requests

    def save_cookies(client):
        with open("cookies.pk", "wb") as f:
            pickle.dump(client.cookies.jar, f)

    def load_cookies():
        if not os.path.isfile("cookies.pk"):
            return None
        with open("cookies.pk", "rb") as f:
            return pickle.load(f)

    # client = httpx.Client(cookies=load_cookies())
    client = requests.Session(cookies=load_cookies())
    save_cookies(client)
