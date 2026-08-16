import subprocess
import sys


def test_import_does_not_require_typing_extensions():
    script = """
import builtins

real_import = builtins.__import__

def block_typing_extensions(name, *args, **kwargs):
    if name == "typing_extensions":
        raise ModuleNotFoundError("typing_extensions blocked for test")
    return real_import(name, *args, **kwargs)

builtins.__import__ = block_typing_extensions
import curl_cffi
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
