#!/bin/sh

CURL_VERSION=curl-8_7_1

curl -L https://github.com/curl/curl/archive/${CURL_VERSION}.zip -o curl.zip
unzip -q -o curl.zip
mv curl-${CURL_VERSION} ${CURL_VERSION}

cd ${CURL_VERSION}

patchfile=../../curl-impersonate/chrome/patches/curl-impersonate.patch
patch -p1 < $patchfile
