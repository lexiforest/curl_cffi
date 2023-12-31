#!/bin/bash

VERSION=$1

# Makefile
gsed "s/^VERSION := .*/VERSION := ${VERSION}/g" -i Makefile

# curl_cffi/__version__.py
gsed "s/^__version__ = .*/__version__ = \"${VERSION}\"/g" -i curl_cffi/__version__.py

# pyproject.toml
gsed "s/^version = .*/version = \"${VERSION}\"/g" -i pyproject.toml
