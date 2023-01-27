clean:
	rm -rf build curl_cffi/*.o curl_cffi/*.so

build:
	python ./prebuild.sh
