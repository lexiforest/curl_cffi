import sys
from setuptools import setup
from wheel.bdist_wheel import bdist_wheel


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        if python.startswith("cp"):
            # on CPython, our wheels are abi3 and compatible back to 3.7
            return "cp37", "abi3", plat

        return python, abi, plat


# this option is only valid in setup.py
kwargs = {"cffi_modules": ["scripts/build.py:ffibuilder"]}
if len(sys.argv) > 1 and sys.argv[1] != 'bdist_wheel':
    kwargs = {}

setup(
    cmdclass={"bdist_wheel": bdist_wheel_abi3},  # type: ignore
    **kwargs,
)
