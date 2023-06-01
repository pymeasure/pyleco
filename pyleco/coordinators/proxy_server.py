#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

"""
Zero MQ Proxy server for data exchange.

methods
-------
pub_sub_proxy
    Listens on port 11100 and publishes to 11099, available to all IP addresses.
pub_sub_remote_proxy
    Connects two local proxy servers on different computers, connecting to their
    publisher port at 11099 and publishing to the local proxy at 11100
start_proxy
    Start a proxy server of either type. If it is merely local, a local server
    is started, otherwise a connecting proxy.


Execute this module to start a proxy server. If no remote connection given, a
local proxy is created (necessary for remote proxies).
command line arguments:
    -v show all the data passing through the proxy
    -s NAME/IP Subscribe to the local proxy of some other computer
    -p NAME/IP Publish to the local proxy of some other computer


Created on Mon Jun 27 09:57:05 2022 by Benedikt Moneke
"""

import logging
import sys
import threading

import zmq

log = logging.Logger(__name__)

port = 11100


# Technical method to start the proxy server. Use `start_proxy` instead.
def pub_sub_proxy(context, captured=False, offset=0):
    """Start a publisher subscriber proxy."""
    log.info(f"Start local proxy server with offset {offset}.")
    s = context.socket(zmq.XSUB)
    p = context.socket(zmq.XPUB)
    s.bind(f"tcp://*:{port - 2 * offset}")
    p.bind(f"tcp://*:{port -1 - 2 * offset}")
    if captured:
        c = context.socket(zmq.PUB)
        c.bind("inproc://capture")
    else:
        c = None
    try:
        zmq.proxy_steerable(p, s, capture=c)
    except zmq.ContextTerminated:
        log.info("Proxy context terminated.")
    except Exception as exc:
        log.exception("Some other exception on proxy happened.", exc)


# Technical method to start the proxy server. Use `start_proxy` instead.
def pub_sub_remote_proxy(context, captured=False, sub="localhost", pub="localhost", offset=0):
    """Start a publisher subscriber remote proxy between two local proxies."""
    log.info(f"Start remote proxy server subsribing to {sub} and publishing to {pub}.")
    s = context.socket(zmq.XSUB)
    p = context.socket(zmq.XPUB)
    s.connect(f"tcp://{sub}:{port -1 - 2 * offset}")
    p.connect(f"tcp://{pub}:{port - 2 * offset}")
    if captured:
        c = context.socket(zmq.PUB)
        c.bind("inproc://capture")
    else:
        c = None
    try:
        zmq.proxy_steerable(p, s, capture=c)
    except zmq.ContextTerminated:
        log.info("Proxy context terminated.")
    except Exception as exc:
        log.exception("Some other exception on proxy happened.", exc)


def start_proxy(context=None, captured=False, sub="localhost", pub="localhost", offset=0):
    """Start a proxy server, either local or remote, in its own thread.

    Examples:

    .. code-block:: python

        # Between software on the local computer, necessary on every computer:
        c = start_proxy()
        # Get the data from a to localhost:
        c = start_proxy(sub="a.domain.com")
        # Send local data to b:
        c = start_proxy(pub="b.domain.com")
        # Send from a to b, can be executed on some third computer:
        c = start_proxy(sub="a.domain.com",
                        pub="b.domain.com")
        # Stop the proxy:
        c.destroy()

    :param context: The zmq context. If None, it generates its own context.
    :param bool captured: Print the captured messages.
    :param str sub: Name or IP Address of the server to subscribe to.
    :param str pub: Name or IP Address of the server to publish to.
    :return: The zmq context. To stop, call `context.destroy()`.
    """
    context = context or zmq.Context.instance()
    if sub == "localhost" and pub == "localhost":
        thread = threading.Thread(target=pub_sub_proxy, args=(context, captured, offset))
    else:
        thread = threading.Thread(target=pub_sub_remote_proxy,
                                  args=(context, captured, sub, pub, offset))
    thread.daemon = True
    thread.start()
    log.info("Proxy thread started.")
    return context


if __name__ == "__main__":
    log.addHandler(logging.StreamHandler())
    captured = True if "-v" in sys.argv else False
    kwargs = {}
    if "-s" in sys.argv:
        try:
            kwargs['sub'] = sys.argv[sys.argv.index("-s") + 1]
        except IndexError:
            pass
    if "-p" in sys.argv:
        try:
            kwargs['pub'] = sys.argv[sys.argv.index("-p") + 1]
        except IndexError:
            pass
    if kwargs:
        print(f"Remote proxy from {kwargs.get('sub', 'localhost')} "
              f"to {kwargs.get('pub', 'localhost')}.")
    else:
        print(
            "This data broker manages the data between measurement software, "
            f"which publishe on port {port}, and all the consumers of data "
            f" (DataLogger, Beamprofiler etc.), which subscribe on port {port -1}."
        )

    context = start_proxy(captured=captured, **kwargs)
    if not kwargs:
        start_proxy(offset=1)  # for log entries
    reader = context.socket(zmq.SUB)
    reader.connect("inproc://capture")
    reader.subscribe(b"")
    poller = zmq.Poller()
    poller.register(reader, zmq.POLLIN)
    while True:
        if input("Quit with q:") == "q":
            context.destroy()
            break
        if socks := dict(poller.poll(100)):
            if reader in socks:
                print("capture", reader.recv_multipart())
