.ONESHELL:
SHELL := bash
VERSION := 0.6.0-alpha.1
CURL_VERSION := curl-8.1.1

.preprocessed: curl_cffi/include/curl/curl.h curl_cffi/cacert.pem .so_downloaded
	touch .preprocessed

curl_cffi/const.py: curl_cffi/include
	python preprocess/generate_consts.py $(CURL_VERSION)

$(CURL_VERSION):
	curl -L "https://curl.se/download/$(CURL_VERSION).tar.xz" \
		-o "$(CURL_VERSION).tar.xz"
	tar -xf $(CURL_VERSION).tar.xz

curl-impersonate-$(VERSION)/chrome/patches: $(CURL_VERSION)
	curl -L "https://github.com/lwthiker/curl-impersonate/archive/refs/tags/v$(VERSION).tar.gz" \
		-o "curl-impersonate-$(VERSION).tar.gz"
	tar -xf curl-impersonate-$(VERSION).tar.gz

curl_cffi/include/curl/curl.h: curl-impersonate-$(VERSION)/chrome/patches
	cd $(CURL_VERSION)
	for p in $</curl-*.patch; do patch -p1 < ../$$p; done
	# Re-generate the configure script
	autoreconf -fi
	mkdir -p ../curl_cffi/include/curl
	cp -R include/curl/* ../curl_cffi/include/curl/

curl_cffi/cacert.pem:
	# https://curl.se/docs/caextract.html
	curl https://curl.se/ca/cacert.pem -o curl_cffi/cacert.pem

.so_downloaded:
	python preprocess/download_so.py $(VERSION)
	touch .so_downloaded

preprocess: .preprocessed
	@echo preprocess

upload: dist/*.whl
	twine upload dist/*.whl

test: install-local
	pytest tests/unittest

install-local: .preprocessed
	pip install -e .

build: .preprocessed
	rm -rf dist/
	pip install build delocate twine
	python -m build --wheel
	delocate-wheel dist/*.whl

clean:
	rm -rf build/ dist/ curl_cffi.egg-info/ $(CURL_VERSION)/ curl-impersonate-$(VERSION)/
	rm -rf curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c curl_cffi/cacert.pem
	rm -rf .preprocessed .so_downloaded $(CURL_VERSION).tar.xz curl-impersonate-$(VERSION).tar.gz
	rm -rf curl_cffi/include/

.PHONY: clean build test install-local upload preprocess
