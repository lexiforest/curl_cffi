clean:
	rm -rf build curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c ./curl-impersonate.tar.gz

build:
	python ./prebuild.sh

build-m1:
    pip install build delocate twine
    python -m build --wheel
    delocate dist/curl_cffi-0.3.1-cp37-abi3-macosx_11_0_arm64.whl
    twine upload dist/*.whl

