from setuptools import setup
from wheel.bdist_wheel import bdist_wheel


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        if python.startswith("cp") and not (python.endswith("t") or abi.endswith("t")):
            if "android" in plat:
                # cibuildwheel supports android since cp313, so we can't mark it as 310
                return python, "abi3", plat
            # On CPython, our wheels are abi3 and compatible back to 3.10.
            # Free-threaded builds ("t" tag) must keep their original tags (PEP 803).
            # Once PEP 803 is accepted, we may be able to build abi3t wheels.
            return "cp310", "abi3", plat

        return python, abi, plat


setup(
    # this option is only valid in setup.py
    cffi_modules=["scripts/build.py:ffibuilder"],
    cmdclass={
        "bdist_wheel": bdist_wheel_abi3,
    },
)
