from setuptools import setup


setup(
    name="curl_cffi",
    packages=["curl_cffi"],
    package_dir={"curl_cffi": "."},
    version="0.1.5",
    author="Yifei Kong",
    description="libcurl ffi bindings for Python",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/yifeikong/curl_cffi",
    setup_requires= ["cffi>=1.0.0"],
    cffi_modules= ["cffi_build.py:ffibuilder"],
    install_requires= ["cffi>=1.0.0"],
    classifiers = [
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.6"
)
