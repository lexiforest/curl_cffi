#!/bin/sh

CURL_VERSION=curl-8_13_0

curl -L https://github.com/curl/curl/archive/${CURL_VERSION}.zip -o curl.zip
unzip -q -o curl.zip
mv curl-${CURL_VERSION} ${CURL_VERSION}

cd ${CURL_VERSION}

patchfile=../../curl-impersonate/patches/curl.patch
patch -p1 < $patchfile
