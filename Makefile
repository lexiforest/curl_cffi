.ONESHELL:
SHELL := bash
VERSION := 0.6.0b9
CURL_VERSION := curl-8.1.1

$(CURL_VERSION):
	curl -L "https://curl.se/download/$(CURL_VERSION).tar.xz" \
		-o "$(CURL_VERSION).tar.xz"
	tar -xf $(CURL_VERSION).tar.xz

	curl -L "https://github.com/yifeikong/curl-impersonate/archive/refs/tags/v$(VERSION).tar.gz" \
		-o "curl-impersonate-$(VERSION).tar.gz"
	tar -xf curl-impersonate-$(VERSION).tar.gz

curl_cffi/include/curl/curl.h: $(CURL_VERSION)
	cd $(CURL_VERSION)
	for p in $</curl-*.patch; do patch -p1 < ../$$p; done
	# Re-generate the configure script
	autoreconf -fi
	mkdir -p ../curl_cffi/include/curl
	cp -R include/curl/* ../curl_cffi/include/curl/

preprocess: curl_cffi/include/curl/curl.h
	@echo generating patched libcurl header files

install-editable: curl_cffi/include/curl/curl.h
	pip install -e .

build: curl_cffi/include/curl/curl.h
	rm -rf dist/
	pip install build
	python -m build --wheel

test:
	python -bb -m pytest tests/unittest

clean:
	rm -rf build/ dist/ curl_cffi.egg-info/ $(CURL_VERSION)/ curl-impersonate-$(VERSION)/
	rm -rf curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c
	rm -rf $(CURL_VERSION).tar.xz curl-impersonate-$(VERSION).tar.gz
	rm -rf curl_cffi/include/

.PHONY: clean build test install-editable preprocess
