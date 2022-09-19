#!/usr/bin/env bash

set -x

# download given curl-impersonate version, then extract to given dir.
VERSION=$1

for arch in aarch64 x86_64; do
    rm lib/Linux-$arch/*
    curl -L -o lib/Linux-$arch-$VERSION.tar.gz \
        https://github.com/lwthiker/curl-impersonate/releases/download/v$VERSION/libcurl-impersonate-v$VERSION.$arch-linux-gnu.tar.gz
    tar -C lib/Linux-$arch -xvzf lib/Linux-$arch-$VERSION.tar.gz
    rm lib/Linux-$arch/libcurl-impersonate-ff*
    rm lib/Linux-$arch/$VERSION.tar.gz
done


# download curl

# extract consts from curl.h
