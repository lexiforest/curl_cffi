import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
import setuptools
from setuptools import Distribution
from setuptools.command.bdist_wheel import bdist_wheel


@pytest.mark.parametrize(
    "version, python, abi, platform, expected",
    [
        ((3, 10), "cp310", "cp310", "linux_x86_64", ("cp310", "abi3")),
        ((3, 15), "cp315", "cp315", "linux_x86_64", ("cp310", "abi3")),
        ((3, 14), "cp314", "cp314t", "linux_x86_64", ("cp314", "cp314t")),
        ((3, 15), "cp315", "cp315t", "linux_x86_64", ("cp315", "abi3.abi3t")),
        ((3, 15), "cp315", "cp315t", "win_amd64", ("cp315", "abi3.abi3t")),
        ((3, 15), "cp315t", "cp315t", "macosx_11_0_arm64", ("cp315", "abi3.abi3t")),
        ((3, 16), "cp316", "cp316t", "linux_x86_64", ("cp315", "abi3.abi3t")),
        ((3, 15), "cp315", "cp315", "android_24_arm64_v8a", ("cp315", "cp315")),
        ((3, 15), "cp315", "cp315t", "android_24_arm64_v8a", ("cp315", "cp315t")),
        ((3, 11), "pp311", "pypy311_pp73", "linux_x86_64", ("pp311", "pypy311_pp73")),
    ],
)
def test_wheel_tag(monkeypatch, version, python, abi, platform, expected):
    monkeypatch.setattr(setuptools, "setup", lambda **kwargs: None)
    monkeypatch.setattr(bdist_wheel, "get_tag", lambda self: (python, abi, platform))
    namespace = runpy.run_path(str(Path(__file__).parents[2] / "setup.py"))
    command = namespace["bdist_wheel_abi3"](Distribution())
    monkeypatch.setitem(
        command.get_tag.__globals__, "sys", SimpleNamespace(version_info=version)
    )

    assert command.get_tag() == (*expected, platform)
