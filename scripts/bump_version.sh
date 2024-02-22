#!/bin/bash

VERSION=$1

# Makefile
gsed "s/^VERSION := .*/VERSION := ${VERSION}/g" -i Makefile

# pyproject.toml
gsed "s/^version = .*/version = \"${VERSION}\"/g" -i pyproject.toml

# build.py
gsed "s/^__version__ = .*/__version__ = \"${VERSION}\"/g" -i scripts/build.py
