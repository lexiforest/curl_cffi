import fnmatch

from setuptools import setup
from setuptools.command.build_py import build_py
from wheel.bdist_wheel import bdist_wheel


class bdist_wheel_abi3(bdist_wheel):
    def get_tag(self):
        python, abi, plat = super().get_tag()

        if python.startswith("cp"):
            # on CPython, our wheels are abi3 and compatible back to 3.7
            return "cp37", "abi3", plat

        return python, abi, plat


excluded = ['curl_cffi/build.py']


class excluded_build_py(build_py):
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [
            (pkg, mod, file)
            for (pkg, mod, file) in modules
            if not any(fnmatch.fnmatchcase(file, pat=pattern) for pattern in excluded)
        ]


setup(
    # this option is only valid in setup.py
    cffi_modules=["curl_cffi/build.py:ffibuilder"],
    cmdclass={"bdist_wheel": bdist_wheel_abi3, 'build_py': excluded_build_py},  # type: ignore
)
