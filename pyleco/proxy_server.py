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

import logging
import sys
import threading

import zmq

log = logging.Logger(__name__)


# Technical method to start the proxy server. Use `start_proxy` instead.
def pub_sub_proxy(context, captured=False):
    """Start a publisher subscriber proxy."""
    log.info("Start local proxy server.")
    s = context.socket(zmq.XSUB)
    p = context.socket(zmq.XPUB)
    s.bind("tcp://*:11100")
    p.bind("tcp://*:11099")
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
def pub_sub_remote_proxy(context, captured=False, sub="localhost", pub="localhost"):
    """Start a publisher subscriber remote proxy between two local proxies."""
    log.info(f"Start remote proxy server subsribing to {sub} and publishing to {pub}.")
    s = context.socket(zmq.XSUB)
    p = context.socket(zmq.XPUB)
    s.connect(f"tcp://{sub}:11099")
    p.connect(f"tcp://{pub}:11100")
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


def start_proxy(context=None, captured=False, sub="localhost", pub="localhost"):
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
        thread = threading.Thread(target=pub_sub_proxy, args=(context, captured))
    else:
        thread = threading.Thread(target=pub_sub_remote_proxy,
                                  args=(context, captured, sub, pub))
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
        print(f"Remote proxy from {kwargs.get('sub', 'localhost')} to {kwargs.get('pub', 'localhost')}.")
    else:
        print(
            "This data broker manages the data between measurement software, "
            "which publishe on port 11100, and all the consumers of data "
            " (DataLogger, Beamprofiler etc.), which subscribe on port 11099."
        )

    context = start_proxy(captured=captured, **kwargs)
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
