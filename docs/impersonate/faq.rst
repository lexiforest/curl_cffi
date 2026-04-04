Impersonation FAQ
=================


How to check if my impersonation is working?
--------------------------------------------

The most reliable way is to use WireShark, and compare packets from ``curl_cffi`` and your
targets.

If it's challenging for you to use WireShark, you can use the following sites for JA3 and Akamai fingerprints:

1. https://tls.browserleaks.com/json
2. https://tls.peet.ws/api/all
3. https://scrapfly.io/web-scraping-tools/browser-fingerprint

For http/3 fingerprints, use our service:

1. https://fp.impersonate.pro/api/http3


I'm still being detected even if I impersonated correctly
---------------------------------------------------------

First, JA3 and akamai fingerprints are not comprehensive, there are other fields that can
be detected, we have a few more options listed in ``extra_fp``. Be sure to also check them.

.. note::

    Since ``curl-impersonate`` was posted on `Hacker News <https://news.ycombinator.com/item?id=42547820>`_,
    some features and behaviors of ``curl_cffi`` is being detected by professional players.
    If we continue to fix these niche behavior in public, it would soon be noticed by those providers.

    In short, if you are using curl_cffi in production and you are sure about being blocked by TLS or http
    detection, try the `curl_cffi pro version <https://impersonate.pro>`_.


Should I randomize my fingerprints for each request?
----------------------------------------------------

You can choose a random version from the list above, like:

.. code-block:: python

    random.choice(["chrome119", "chrome120", ...])

However, be aware of the browser market share, very old versions are not good choices.

Generally, you should not try to generate a customized random fingerprints. The reason
is that, for a given browser version, the fingerprints are fixed. If you create a new
random fingerprints, the server is easy to know that you are not using a typical browser.

If you were thinking about ``ja3``, and not ``ja3n``, then the fingerprints is already
randomized, due to the ``extension permutation`` feature introduced in Chrome 110.

As far as we know, most websites use an allowlist, not a blocklist to filter out bot
traffic. So do not expect random ja3 fingerprints would work in the wild.

Moreover, do not generate random ja3 strings. There are certain limits for a valid ja3 string.
For example:

* TLS 1.3 ciphers must be at the front.
* GREASE extension must be the first.
* etc.

You should copy ja3 strings from sniffing tools, not generate them, unless you can make
sure all the requirements are met.

Can I change JavaScript fingerprints with this library?
-------------------------------------------------------

No, you can not. As the name suggests, JavaScript fingerprints are generated using JavaScript
APIs provided by real browsers. ``curl_cffi`` is a python binding to a C library, with no
browser or JavaScript runtime under the hood.

If you need to impersonate browsers on the JavaScript perspective, you can search for
"Anti-detect Browser", "Playwright stealth" and similar keywords. Or simply use a
commercial plan from our sponsors.


Why are all the User-Agents macOS?
----------------------------------

Simple, because I primarily use macOS and I copied the headers from my own browser. Fingerprints
are generally the same across desktop OSes, if you want it to look like Windows, just update the
user-agent and other related headers to Windows.

