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
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "scrapfly.png"),
            },
        ]
    )

    r = requests.post(file_server.url + "/file", multipart=multipart)
    data = r.json()
    assert data["filename"] == "scrapfly.png"
    assert data["content_type"] == "image/jpg"
    assert data["size"] == os.path.getsize(ASSET_FOLDER / "scrapfly.png")
    multipart.close()


def test_upload_with_text_fields(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "image",
                "content_type": "image/jpg",
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "scrapfly.png"),
            },
            {"name": "foo", "data": b"bar"},
        ]
    )

    r = requests.post(file_server.url + "/file", data={"foo": "bar"}, multipart=multipart)
    data = r.json()
    assert data["filename"] == "scrapfly.png"
    assert data["content_type"] == "image/jpg"
    assert data["size"] == os.path.getsize(ASSET_FOLDER / "scrapfly.png")
    assert data["foo"] == "bar"
    multipart.close()


def test_upload_multiple_files(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "images",
                "content_type": "image/jpg",
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "scrapfly.png"),
            },
            {
                "name": "images",
                "content_type": "image/jpg",
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "scrapfly.png"),
            },
        ]
    )

    r = requests.post(file_server.url + "/files", multipart=multipart)
    data = r.json()
    assert len(data["files"]) == 2
    assert data["files"][0]["filename"] == "scrapfly.png"
    assert data["files"][0]["content_type"] == "image/jpg"
    assert data["files"][0]["size"] == os.path.getsize(ASSET_FOLDER / "scrapfly.png")
    multipart.close()


def test_upload_multiple_files_different_name(file_server):
    multipart = CurlMime.from_list(
        [
            {
                "name": "image1",
                "content_type": "image/jpg",
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "scrapfly.png"),
            },
            {
                "name": "image2",
                "content_type": "image/jpg",
                "filename": "scrapfly.png",
                "local_path": str(ASSET_FOLDER / "yescaptcha.png"),
            },
        ]
    )

    r = requests.post(file_server.url + "/two-files", multipart=multipart)
    data = r.json()
    assert data["size1"] == os.path.getsize(ASSET_FOLDER / "scrapfly.png")
    assert data["size2"] == os.path.getsize(ASSET_FOLDER / "yescaptcha.png")
    multipart.close()
