JA4 support in curl-cffi
========================

This page is intentionally opinionated.

JA4 is often presented as the natural successor to JA3, but for browser
impersonation and practical protocol debugging, it is mostly a repackaging of
things we already had, plus a few design choices that make analysis less clear,
not more.

The name is misleading, it has nothing to do with JA3 or its creators. If your goal
is exact impersonation, reproducibility, and debugging of TLS client hellos,
simply set the ``ja3=...`` and ``extra_fp=...`` parameters in curl_cffi, which
already covers what ``ja4`` claims to cover.

This page assumes that you have learned what JA4 is. If otherwise, just don't use it.


What JA3 Already Gives You
--------------------------

JA3 is not comprehensive, but it does its job: a digest of TLS client hello.

The original JA3 method from Salesforce takes a client hello and builds a
canonical text value from:

- TLS version
- cipher suites
- extension list
- supported groups
- EC point formats

That text value is then hashed with MD5 easier matching.

This matters because JA3 has a clean separation between two different use cases:

1. The raw text value is for humans, debugging, and reproduction.
2. The hash is for compact indexing and correlation.

That split is simple and useful.

- When a request is blocked, you can compare the JA3 text values, it's easier for human eyes.
- When you need a small key for a database, the hash is there.

However, JA3 is not complete, and it never claimed to be. As time goes by, some extra
bits in the TLS hellp packet have been utilized to distinguish between bots and humans.
And that's why we have an ``extra_fp`` parameter.


What JA4 Adds, and Why That Is Not Very Useful
----------------------------------------------

The official JA4 material says the new format is more human readable, supports
QUIC, exposes ALPN, and allows partial matching via the ``a_b_c`` structure.
Those are real changes, but they are much less valuable than the marketing
around them suggests.

The JA4 propaganda says that JA3 is obsolete because Chrome introduces the extension
permutation in version 110+, so JA3 does not make sense anymore.

This is simply overstating. To counter TLS extension permutation, just use ``ja3n``,
sorting the extension is not a big deal as JA4 authors said.

Being able to say "these two fingerprints share the same a+c parts" may be
useful in a threat-hunting product. It is not especially useful if you are
trying to answer questions like:

- Why did this browser fingerprint stop working?
- Which extension changed?
- Did the ALPN change, or the signature algorithms, or both?
- What exact client hello do I need to reproduce?

In those situations, the right answer is not another derived label. The right
answer is the actual structured handshake data.

So JA4 is not even an upgrade from JA3. It is mostly a different tradeoff, presented
as a universal improvement.


Mixing Text and Hashes Is a Bad Design
--------------------------------------

The worst design choice in JA4 is that it mixes readable text and hashed
segments into a single first-class value.

The result looks tidy:

.. code-block:: text

    t13d1516h2_8daaf6152771_02713d6af862

But this tidiness is deceptive.

The first segment is somewhat interpretable by a human. The later segments are
opaque hashes. So the value is neither properly human readable nor properly
machine-minimal. It sits in the worst middle ground:

- too encoded for direct debugging
- too lossy for reproduction
- too clever for casual inspection

Compare that with JA3:

- raw text for inspection
- hash for indexing

That design is boring, and that is exactly why it is good.

If you see two JA3 text values, you can compare them directly.
If you see two JA4 values and one hashed segment changes, you learn almost
nothing without a second decoding step or an external lookup table.

This is especially annoying in debugging. Suppose a target starts
rejecting a fingerprint after a browser update. With JA3-style raw text, you can
look at the changed cipher list or extension list and reason about the delta.
With JA4, the pretty-looking value hides the interesting part behind hashes.

That is not "more readable". It is more confusing, for both humans and machines.

The sane design would have been:

1. define a normalized text representation and expose that text directly,
2. optionally hash it for compact storage.

JA3 already had that basic idea right, and for permutation, just use ja3n

JA4 instead tries to make one value serve as both explanation and identifier.
That is usually a mistake. Explanation and identification are different jobs.


Conclusion
----------

JA4 is not worthless. If your only goal is coarse clustering in a defensive
analytics pipeline, some of its normalization choices may be convenient.

But convenience for clustering is not the same as usefulness for
impersonation, protocol debugging, or exact client reproduction.

JA3 already gave us a simple and honest model:

- here is the concrete handshake text
- here is a compact hash of it

JA4 adds structure, but forcing human to read hashes is simply not a very clever
abstraction.

If you want to understand or reproduce a TLS fingerprint, you want the handshake packet,
not a buzzword. JA3 is a useful human-readable format, and there is not point in using
the JA4 string.

``curl_cffi`` focuses on the impersonation of the entire hello packet, not a representation
string. So to answer is ``ja4`` supported in ``curl_cffi``?

- Yes, by supporting the entire packet, ja4 is just part of it.
- No, we do not accept ``ja4`` as a input string, because it's a hash and not parsable.


References
----------

- `JA3: A method for profiling SSL/TLS Clients <https://github.com/salesforce/ja3>`_
- `TLS Fingerprinting with JA3 and JA3S <https://engineering.salesforce.com/tls-fingerprinting-with-ja3-and-ja3s-247362855967>`_
- `JA4+ Network Fingerprinting <https://blog.foxio.io/ja4%2B-network-fingerprinting>`_
- `FoxIO JA4 repository <https://github.com/FoxIO-LLC/ja4>`_
