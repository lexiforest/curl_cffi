clean:
	rm -rf build curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c ./curl-impersonate.tar.gz

build:
	python ./prebuild.sh
