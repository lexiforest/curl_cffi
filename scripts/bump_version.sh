#!/bin/bash

VERSION=$1
UPSTREAM_VERSION=$2

# Makefile
gsed "s/^VERSION := .*/VERSION := ${UPSTREAM_VERSION}/g" -i Makefile

# pyproject.toml
gsed "s/^version = .*/version = \"${VERSION}\"/g" -i pyproject.toml

# build.py
gsed "s/^__version__ = .*/__version__ = \"${UPSTREAM_VERSION}\"/g" -i scripts/build.py
