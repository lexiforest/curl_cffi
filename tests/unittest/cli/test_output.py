import argparse

import pytest

from curl_cffi.const import CurlHttpVersion
from curl_cffi.cli.output import (
    _http_ver_label,
    _sanitize_filename,
    determine_print_spec,
)


@pytest.mark.parametrize(
    "version, expected",
    [
        (CurlHttpVersion.V1_0, "1.0"),
        (CurlHttpVersion.V1_1, "1.1"),
        (CurlHttpVersion.V2_0, "2"),
        (CurlHttpVersion.V2TLS, "2"),
        (CurlHttpVersion.V2_PRIOR_KNOWLEDGE, "2"),
        (CurlHttpVersion.V3, "3"),
        (CurlHttpVersion.V3ONLY, "3"),
        (999, "1.1"),
    ],
)
def test_http_ver_label(version, expected):
    r = argparse.Namespace(http_version=version)
    assert _http_ver_label(r) == expected


def _make_args(**overrides):
    defaults = dict(
        print_spec=None,
        verbose=False,
        headers_only=False,
        body_only=False,
        download=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


@pytest.mark.parametrize(
    "overrides, expected",
    [
        (dict(print_spec="Hh"), "Hh"),
        (dict(verbose=True), "HhBb"),
        (dict(headers_only=True), "h"),
        (dict(body_only=True), "b"),
        (dict(download=True), "h"),
    ],
)
def test_determine_print_spec(overrides, expected):
    assert determine_print_spec(_make_args(**overrides)) == expected


@pytest.mark.parametrize(
    "input, expected",
    [
        ("report.pdf", "report.pdf"),
        ("../../etc/passwd", "passwd"),
        ("C:\\Users\\test\\file.txt", "file.txt"),
        ("file name (1).txt", "file_name__1_.txt"),
        ("file\x00name.txt", "filename.txt"),
        ("", "download"),
        ("???", "___"),
    ],
)
def test_sanitize_filename(input, expected):
    assert _sanitize_filename(input) == expected
