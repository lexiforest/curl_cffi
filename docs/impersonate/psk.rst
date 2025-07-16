TLS PSK(41) Extension
=====================


What is the TLS PSK(41) extension, how to deal with it?

PSK is short for ``Pre-Shared Key``, as defined in `RFC 8446 <https://www.rfc-editor.org/rfc/rfc8446.html#section-2.2>`_,

  Once a handshake has completed, the server can send the client a PSK
  identity that corresponds to a unique key derived from the initial
  handshake (see Section 4.6.1).  The client can then use that PSK
  identity in future handshakes to negotiate the use of the associated
  PSK.

Usually, when you first visit a website, the PSK extension is not present in the extension
list. But when you visit the same website for the second time, in a relatively short time,
the client may offer a PSK extension with the key from the server.

For example, you can visit ``https://tls.peet.ws/api/all``, and then refresh the page,
the PSK extension will be there.

To correctly implement the PSK extension, the client must have some kind of a session
cache held in memory or persisted on disk. All the major browsers have this feature for
a very long time. ``curl_cffi`` added this feature in version ``0.11.0``, with libcurl
``8.13.0``.

The mechanism and behavior of a PSK looks like an http session cookie, where the server sent
a cryptographic value as a key to resume a previous disconnected session. When the server generates
a PSK, it is possible that the server keeps the mapping between the incoming IP and key.
Thus, it can be problematic if you reuse a TLS session with rotating proxies.

.. code-block::

    ┌───────────┐                                    ┌───────────┐
    │           │                                    │           │
    │           │             IP: 10.0.0.1           │           │
    │           ┼─────────────TLS─Hello──────────────►           │
    │           │                                    │           │
    │           ◄─────────────PSK:─xxx───────────────┼           │
    │           │                                    │           │
    │           │                                    │           │
    │           │                                    │           │
    │           │                                    │  Server   │
    │  Client   │             IP: 10.0.0.2           │           │
    │           ┼─────────────TLS─with─PSK───────────►           │
    │           │                                    │           │
    │           ◄─────────────Blocked────────────────┼           │
    │           │                                    │           │
    │           │             PSK: xxx was           │           │
    │           │             associated with        │           │
    │           │             10.0.0.1, not          │           │
    └───────────┘             10.0.0.2               └───────────┘


Luckily, since curl_cffi ``0.12.0``, we added a new option called ``proxy_credential_no_reuse``,
when enabled, the TLS session cache will be bound based on the proxy username and IP,
such that the session can only be reused when the proxy username and IP matches. From the
server's viewpoint, the ``Pre-Shared Key`` will be locked to the same source IP, not
bouncing around among different exit nodes.


.. code-block:: python

   # Python example to be added.
   # We might enable this by default when proxies are used.


How do I enable PSK extension anyway?
-------------------------------------

You don't. If you haven't, please read the explanation above first. Generally speaking,
the client should manage this extension, and it should automatically offer this extension
on the second request.

From the server's perspective, if you forcefully add a PSK extension with random value,
it's an obvious sign that you are not a valid visitor, just like you providing an invalid cookie
value.

However, it's reasonable that you don't want the PSK extension to be sent, i.e. pretending
to be a first time visitor. We don't support this for now, your option is to use an older
version of curl_cffi or create a new session on each request.

Note, some other impersonation-oriented http clients give you the control over adding the
PSK or not, but you should let the client decide, if you are trying to impersonating browsers.


References:

1. https://github.com/icing/blog/blob/main/curl-sessions-earlydata.md
