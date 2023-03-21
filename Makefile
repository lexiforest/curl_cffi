clean:
	rm -rf build/ curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c ./curl-impersonate.tar.gz

build:
	python ./prebuild.sh

upload-m1: build-m1
	twine upload dist/*.whl

build-m1:
	rm -rf dist/
	pip install build delocate twine
	python -m build --wheel
	delocate-wheel dist/*.whl
