import sys

from setuptools import setup

try:
    # integrated since setuptools 70.1, avoids wheel's bdist_wheel FutureWarning
    from setuptools.command.bdist_wheel import bdist_wheel
except ImportError:
    from wheel.bdist_wheel import bdist_wheel


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        # Android extension modules link libpython3.X.so by SONAME, so they are not
        # stable-ABI across minor versions even though they are built against the
        # limited API. Keep the real tag there and ship one wheel per CPython minor,
        # otherwise pip installs the 3.13 wheel on 3.14 and the import fails, see #824.
        if python.startswith("cp") and "android" not in plat:
            if python.endswith("t") or abi.endswith("t"):
                # CFFI targets both stable ABIs on free-threaded Python 3.15+.
                if sys.version_info >= (3, 15):
                    return "cp315", "abi3.abi3t", plat
                return python, abi, plat

            # GIL-enabled builds remain compatible back to 3.10.
            return "cp310", "abi3", plat

        return python, abi, plat


setup(
    # this option is only valid in setup.py
    cffi_modules=["scripts/build.py:ffibuilder"],
    cmdclass={
        "bdist_wheel": bdist_wheel_abi3,
    },
)
