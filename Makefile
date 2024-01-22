.ONESHELL:
SHELL := bash
VERSION := 0.6.0b8
CURL_VERSION := curl-8.1.1

.preprocessed: curl_cffi/include/curl/curl.h
	touch .preprocessed

curl_cffi/const.py: curl_cffi/include
	python preprocess/generate_consts.py $(CURL_VERSION)

$(CURL_VERSION):
	curl -L "https://curl.se/download/$(CURL_VERSION).tar.xz" \
		-o "$(CURL_VERSION).tar.xz"
	tar -xf $(CURL_VERSION).tar.xz

curl-impersonate-$(VERSION)/chrome/patches: $(CURL_VERSION)
	curl -L "https://github.com/yifeikong/curl-impersonate/archive/refs/tags/v$(VERSION).tar.gz" \
		-o "curl-impersonate-$(VERSION).tar.gz"
	tar -xf curl-impersonate-$(VERSION).tar.gz

# TODO add the headers to sdist package
curl_cffi/include/curl/curl.h: curl-impersonate-$(VERSION)/chrome/patches
	cd $(CURL_VERSION)
	for p in $</curl-*.patch; do patch -p1 < ../$$p; done
	# Re-generate the configure script
	autoreconf -fi
	mkdir -p ../curl_cffi/include/curl
	cp -R include/curl/* ../curl_cffi/include/curl/

preprocess: .preprocessed
	@echo preprocess

upload: dist/*.whl
	twine upload dist/*.whl

test:
	python -bb -m pytest tests/unittest

install-local: .preprocessed
	pip install -e .

build: .preprocessed
	rm -rf dist/
	pip install build delocate twine
	python -m build --wheel
	delocate-wheel dist/*.whl

clean:
	rm -rf build/ dist/ curl_cffi.egg-info/ $(CURL_VERSION)/ curl-impersonate-$(VERSION)/
	rm -rf curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c
	rm -rf .preprocessed .so_downloaded $(CURL_VERSION).tar.xz curl-impersonate-$(VERSION).tar.gz
	rm -rf curl_cffi/include/

.PHONY: clean build test install-local upload preprocess
