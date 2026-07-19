import importlib.util
import shutil
import urllib.request
from pathlib import Path


LIBRARY_FILENAMES = (
    "libcurl-impersonate.a",
    "libcurl-impersonate.so",
    "libcurl-impersonate.dll",
)


def create_libraries(directory):
    for filename in LIBRARY_FILENAMES:
        (directory / filename).touch()


def load_build():
    build_path = Path(__file__).parents[2] / "scripts/build.py"
    spec = importlib.util.spec_from_file_location("curl_cffi_build", build_path)
    assert spec is not None
    assert spec.loader is not None
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    return build


def test_impersonate_build_dir_reuses_existing_library(monkeypatch, tmp_path):
    create_libraries(tmp_path)

    def fail_download(*args, **kwargs):
        raise AssertionError("existing library should not be downloaded again")

    monkeypatch.setenv("IMPERSONATE_BUILD_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlretrieve", fail_download)

    build = load_build()

    assert build.libdir == tmp_path


def test_impersonate_build_dir_selects_download_destination(monkeypatch, tmp_path):
    downloads = []

    def record_download(url, filename):
        downloads.append((url, filename))

    def unpack_library(filename, directory):
        assert filename == "libcurl-impersonate.tar.gz"
        assert Path(directory) == tmp_path
        create_libraries(tmp_path)

    monkeypatch.setenv("IMPERSONATE_BUILD_DIR", str(tmp_path))
    monkeypatch.setattr(urllib.request, "urlretrieve", record_download)
    monkeypatch.setattr(shutil, "unpack_archive", unpack_library)

    build = load_build()

    assert build.libdir == tmp_path
    assert len(downloads) == 1
