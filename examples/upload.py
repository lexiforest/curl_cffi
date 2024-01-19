"""
We do not support requests.post(url, files=...), for 2 reasons.

- Curl's mime struct need to be freed manually after each request.
- requests' files parameter is quite a mess, it's just not worth it.

You use the multipart instead, it's very simple and straightforward.
"""
from curl_cffi import requests, CurlMime


form = CurlMime()
form.addpart(
    "image",  # form field name
    type="image/png",  # mime type
    filename="image.png",  # filename seen by remote server
    filepath="./image.png",  # local file to upload
)

# you can add multiple files under the same field name
form.addpart(
    "image",
    type="image/jpg",
    filename="image.jpg",
    fileobj=open("./image.jpg"),  # local file to upload, not the difference vs above
)

# from a list
form = CurlMime.from_list(
    [
        {
            "name": "image",
            "type": "image/png",
            "filename": "image.png",
            "filepath": "./image.png",
        },
    ]
)

r = requests.get(url, multipart=form)

# close the form object, otherwise you have to wait for GC to recycle it. If you files
# are too large, you may run out of memory quickly.
form.close()
