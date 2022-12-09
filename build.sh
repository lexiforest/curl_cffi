#!/usr/bin/env bash

set -x

CURL_IMPERSONATE_VERSION=0.5.3
CURL_VERSION=7.84
ARCH=$(arch)
LIBDIR=./libcurl

# download given curl-impersonate version, then extract to given dir.
rm -rf $LIBDIR
mkdir $LIBDIR
curl -L -o /tmp/${ARCH}-${VERSION}.tar.gz \
    https://github.com/lwthiker/curl-impersonate/releases/download/v${VERSION}/libcurl-impersonate-v${VERSION}.${ARCH}-linux-gnu.tar.gz
tar -C $LIBDIR/Linux-$arch -xvzf $LIBDIR/$arch-$VERSION.tar.gz
rm $LIBDIR/libcurl-impersonate-ff*
rm $LIBDIR/$arch/$VERSION.tar.gz

# download curl

# extract consts from curl.h
