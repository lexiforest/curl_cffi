import os
from pathlib import Path

from curl_cffi import CurlMime, requests

ASSET_FOLDER = Path(__file__).parent.parent.parent / "assets"


def test_upload_single_file(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "image",
                "content_type": "image/jpg",
                "filename": "alipay.jpg",
                "local_path": str(ASSET_FOLDER / "alipay.jpg"),
            },
        ]
    )

    r = requests.post(file_server.url + "/file", multipart=multipart)
    data = r.json()
    assert data["filename"] == "alipay.jpg"
    assert data["content_type"] == "image/jpg"
    assert data["size"] == os.path.getsize(ASSET_FOLDER / "alipay.jpg")
    multipart.close()


def test_upload_with_text_fields(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "image",
                "content_type": "image/jpg",
                "filename": "alipay.jpg",
                "local_path": str(ASSET_FOLDER / "alipay.jpg"),
            },
            {"name": "foo", "data": b"bar"},
        ]
    )

    r = requests.post(file_server.url + "/file", data={"foo": "bar"}, multipart=multipart)
    data = r.json()
    assert data["filename"] == "alipay.jpg"
    assert data["content_type"] == "image/jpg"
    assert data["size"] == os.path.getsize(ASSET_FOLDER / "alipay.jpg")
    assert data["foo"] == "bar"
    multipart.close()


def test_upload_multiple_files(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "images",
                "content_type": "image/jpg",
                "filename": "alipay.jpg",
                "local_path": str(ASSET_FOLDER / "alipay.jpg"),
            },
            {
                "name": "images",
                "content_type": "image/jpg",
                "filename": "wechat.jpg",
                "local_path": str(ASSET_FOLDER / "wechat.jpg"),
            },
        ]
    )

    r = requests.post(file_server.url + "/files", multipart=multipart)
    data = r.json()
    assert len(data["files"]) == 2
    assert data["files"][0]["filename"] == "alipay.jpg"
    assert data["files"][0]["content_type"] == "image/jpg"
    assert data["files"][0]["size"] == os.path.getsize(ASSET_FOLDER / "alipay.jpg")
    multipart.close()


def test_upload_multiple_files_different_name(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "image1",
                "content_type": "image/jpg",
                "filename": "alipay.jpg",
                "local_path": str(ASSET_FOLDER / "alipay.jpg"),
            },
            {
                "name": "image2",
                "content_type": "image/jpg",
                "filename": "wechat.jpg",
                "local_path": str(ASSET_FOLDER / "wechat.jpg"),
            },
        ]
    )

    r = requests.post(file_server.url + "/two-files", multipart=multipart)
    data = r.json()
    assert data["size1"] == os.path.getsize(ASSET_FOLDER / "alipay.jpg")
    assert data["size2"] == os.path.getsize(ASSET_FOLDER / "wechat.jpg")
    multipart.close()
