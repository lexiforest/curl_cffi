# Compatibility with requests

Although we try our best to mimic the requests API, some functionality is not easy to implement and left out.
Here are a list of known incompatibilities:

- retries are not supported yet, tracked in [#24](https://github.com/yifeikong/curl_cffi/issues/24)
- stream/iterate are not supported. tracked in [#26](https://github.com/yifeikong/curl_cffi/issues/26)
- files are not supported.
- session cookies may lost during redirects, tracked in [#55](https://github.com/yifeikong/curl_cffi/issues/55)
- redirect history are not supported, tracked in [#82](https://github.com/yifeikong/curl_cffi/issues/82)
