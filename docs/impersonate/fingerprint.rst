What is TLS and http/2, http/3 fingerprinting?
----------------------------------------------

TLS and http/2
~~~~~~~~~~~~~~

TLS is the ``s`` in ``https``. ``https`` has been uniformly deployed across the world.
There are many extension and cipher suites a implementation can choose to use. According to
the RFC, there are many valid combinations. But in reality, browser vendors tend to use
fixed combinations, and these combinations can be used identify if the request is from a
certain browser or an automated script. The digest of this combination is called a TLS
fingerprints. The most common digesting method is called `JA3`.

Similar to TLS, there are a few settings in http/2 connection can be used to identify the
source of a request. The most commonly used digesting method is proposed by Akamai, and called
the Akamai http2 fingerprint.

To learn the details of TLS and http2 fingerprinting, you can read these great articles from lwthiker:

1. https://lwthiker.com/networks/2022/06/17/tls-fingerprinting.html
2. https://lwthiker.com/networks/2022/06/17/http2-fingerprinting.html

The format of JA3 and Akamai digest is briefly discussed below.

http/3
~~~~~~

As of http/3, the newest version of http. Basically, it's http/2 reimplemented over QUIC,
thus it can be fingerprinted in a similar way with http/2.

Http/3 fingerprints has not yet been publicly exploited and reported. But given the rapidly increasing
marketshare of http/3(35% of internet traffic), it is expected that some strict WAF vendors have begun
to utilize http/3 fingerprinting.

It has also been noticed by many users, that, for a lot of sites, there is less or even none
detection when using http/3.

To check your browser's http3 & quic fingerprints, you can visit our `http/3 & quic fingerprints API <https://fp.impersonate.pro>`_ page.

``curl_cffi`` provides TLS and http/2 impersonation and http/3 protocol. Http/3 fingerprints
support and UDP proxy support will be added in v0.15.

