#!/bin/bash

VERSION=$1
UPSTREAM_VERSION=$2
CURL_VERSION=$3

# Makefile
gsed "s/^VERSION := .*/VERSION := ${UPSTREAM_VERSION}/g" -i Makefile
if [ -n "${CURL_VERSION}" ]; then
    gsed "s/^CURL_VERSION := .*/CURL_VERSION := ${CURL_VERSION}/g" -i Makefile
    gsed "s/^CURL_VERSION=.*/CURL_VERSION=${CURL_VERSION}/g" -i scripts/download_curl.sh
fi

# pyproject.toml
gsed "s/^version = .*/version = \"${VERSION}\"/g" -i pyproject.toml

# build.py
gsed "s/^__version__ = .*/__version__ = \"${UPSTREAM_VERSION}\"/g" -i scripts/build.py
