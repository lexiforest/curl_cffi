#!/bin/bash

VERSION=$1

# Makefile
gsed "s/^VERSION := .*/VERSION := ${VERSION}/g" -i Makefile

# pyproject.toml
gsed "s/^version = .*/version = \"${VERSION}\"/g" -i pyproject.toml

# setup.py
gsed "s/^__version__ = .*/__version__ = \"${VERSION}\"/g" -i setup.py
