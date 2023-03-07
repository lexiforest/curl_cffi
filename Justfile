clean:
	rm -rf build curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c ./curl-impersonate.tar.gz

build:
	python ./prebuild.sh

build-m1:
    rm dist/*
    pip install build delocate twine
    python -m build --wheel
    delocate-wheel dist/*.whl
    twine upload dist/*.whl

