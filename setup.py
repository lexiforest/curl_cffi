import sysconfig

from setuptools import setup
from wheel.bdist_wheel import bdist_wheel


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        gil_disabled = sysconfig.get_config_var("Py_GIL_DISABLED")

        if python.startswith("cp") and not gil_disabled:
            # on CPython, our wheels are abi3 and compatible back to 3.9
            return "cp39", "abi3", plat

        return python, abi, plat


setup(
    # this option is only valid in setup.py
    cffi_modules=["scripts/build.py:ffibuilder"],
    cmdclass={
        "bdist_wheel": bdist_wheel_abi3,
    },
)
