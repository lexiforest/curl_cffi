.ONESHELL:
SHELL := bash

# this is the upstream libcurl-impersonate version
VERSION := 1.4.2
CURL_VERSION := curl-8_15_0

$(CURL_VERSION):
	curl -L https://github.com/curl/curl/archive/$(CURL_VERSION).zip -o curl.zip
	unzip -q -o curl.zip
	mv curl-$(CURL_VERSION) $(CURL_VERSION)

curl-impersonate-$(VERSION)/patches: $(CURL_VERSION)
	curl -L "https://github.com/lexiforest/curl-impersonate/archive/refs/tags/v$(VERSION).tar.gz" \
		-o "curl-impersonate-$(VERSION).tar.gz"
	tar -xf curl-impersonate-$(VERSION).tar.gz

.preprocessed: curl-impersonate-$(VERSION)/patches
	cd $(CURL_VERSION)
	# for p in $</curl*.patch; do patch -p1 < ../$$p; done
	patch -p1 < ../$</curl.patch
	# Re-generate the configure script
	autoreconf -fi
	mkdir -p ../include/curl
	cp -R include/curl/* ../include/curl/
	# Sentinel files: https://tech.davis-hansson.com/p/make/
	cd ..
	touch .preprocessed

local-curl: $(CURL_VERSION)
	cp /usr/local/lib/libcurl-impersonate* /Users/runner/work/_temp/install/lib/
	cd $(CURL_VERSION)
	for p in ../curl-impersonate/patches/curl*.patch; do patch -p1 < ../$$p; done
	# Re-generate the configure script
	autoreconf -fi
	mkdir -p ../include/curl
	cp -R include/curl/* ../include/curl/
	# Sentinel files: https://tech.davis-hansson.com/p/make/
	touch .preprocessed

gen-const:
	python scripts/generate_consts.py $(CURL_VERSION)

preprocess: .preprocessed
	@echo generating patched libcurl header files

install-editable:
	pip install -e .

build: .preprocessed
	rm -rf dist/
	pip install build
	python -m build --wheel

lint:
	ruff check --exclude issues

format:
	ruff format --exclude issues

test:
	python -bb -m pytest tests/unittest

clean:
	rm -rf build/ dist/ curl_cffi.egg-info/ $(CURL_VERSION)/ curl-impersonate-$(VERSION)/
	rm -rf curl_cffi/*.o curl_cffi/*.so curl_cffi/_wrapper.c
	rm -rf .preprocessed $(CURL_VERSION).tar.xz curl-impersonate-$(VERSION).tar.gz
	rm -rf include/

.PHONY: clean build test install-editable preprocess gen-const
