"""
We do not support requests.post(url, files=...), for 2 reasons.

- Curl's mime struct need to be freed manually after each request.
- requests' files parameter is quite a mess, it's just not worth it.

You use the multipart instead, it's very simple and straightforward.
"""

from curl_cffi import CurlMime, requests

mp = CurlMime()
mp.addpart(
    name="image",  # form field name
    content_type="image/png",  # mime type
    filename="image.png",  # filename seen by remote server
    local_path="./image.png",  # local file to upload
)

with open("./image.jpg", "rb") as file:
    data = file.read()

# you can add multiple files under the same field name
mp.addpart(
    name="image",
    content_type="image/jpg",
    filename="image.jpg",
    data=data,  # note the difference vs above
)

# from a list
mp = CurlMime.from_list(
    [
        {
            "name": "text",
            "content_type": "text/plain",
            "filename": "test.txt",
            "local_path": "./test.txt",
        },
        {
            "name": "foo",
            "content_type": "text/plain",
            "filename": "another.txt",
            "data": "bar",
        },
    ]
)

r = requests.post("https://httpbin.org/post", data={"foo": "bar"}, multipart=mp)
print(r.json())

# close the form object, otherwise you have to wait for GC to recycle it. If you files
# are too large, you may run out of memory quickly.
mp.close()
