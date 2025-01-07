#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2025 PyLECO Developers
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
    Run a publisher subscriber proxy in the current thread (blocking).
start_proxy
    Start a proxy server, either local or remote, in its own thread.


Execute this module to start a proxy server. If no remote connection given, a
local proxy is created (necessary for remote proxies).
command line arguments:
    -v show all the data passing through the proxy
    -s NAME/IP Subscribe to the local proxy of some other computer
    -p NAME/IP Publish to the local proxy of some other computer

Created on Mon Jun 27 09:57:05 2022 by Benedikt Burger
"""

from __future__ import annotations
import logging
import threading
from typing import Optional

import zmq

if __name__ == "__main__":
    from pyleco.core import PROXY_RECEIVING_PORT
else:
    from ..core import PROXY_RECEIVING_PORT


log = logging.Logger(__name__)

port = PROXY_RECEIVING_PORT


# Technical method to start the proxy server. Use `start_proxy` instead.
def pub_sub_proxy(
    context: zmq.Context,
    captured: bool = False,
    sub: str = "localhost",
    pub: str = "localhost",
    offset: int = 0,
    event: Optional[threading.Event] = None,
) -> None:
    """Run a publisher subscriber proxy in the current thread (blocking)."""
    s: zmq.Socket = context.socket(zmq.XSUB)
    p: zmq.Socket = context.socket(zmq.XPUB)
    _port = port - 2 * offset
    if sub == "localhost" and pub == "localhost":
        log.info(f"Start local proxy server: listening on {_port}, publishing on {_port - 1}.")
        s.bind(f"tcp://*:{_port}")
        p.bind(f"tcp://*:{_port - 1}")
    else:
        log.info(
            f"Start remote proxy server subsribing to {sub}:{_port - 1} and publishing to "
            f"{pub}:{_port}."
        )
        s.connect(f"tcp://{sub}:{port -1 - 2 * offset}")
        p.connect(f"tcp://{pub}:{port - 2 * offset}")

    if captured:
        log.info("Capturing all messages.")
        c: zmq.Socket = context.socket(zmq.PUB)
        c.bind("inproc://capture")
    else:
        c = None  # type: ignore
    if event is not None:
        event.set()
    try:
        zmq.proxy_steerable(p, s, capture=c)
    except zmq.ContextTerminated:
        log.info("Proxy context terminated.")
    except Exception as exc:
        log.exception("Some other exception on proxy happened.", exc)


def start_proxy(
    context: Optional[zmq.Context] = None,
    captured: bool = False,
    sub: str = "localhost",
    pub: str = "localhost",
    offset: int = 0,
) -> zmq.Context:
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

    :param context: The zmq context.
    :param bool captured: Print the captured messages.
    :param str sub: Name or IP Address of the server to subscribe to.
    :param str pub: Name or IP Address of the server to publish to.
    :param offset: How many servers (pairs of ports) to offset from the base one.
    :return: The zmq context. To stop, call `context.destroy()`.
    """
    context = context or zmq.Context.instance()
    event = threading.Event()
    thread = threading.Thread(
        target=pub_sub_proxy, args=(context, captured, sub, pub, offset, event)
    )
    thread.daemon = True
    thread.start()
    started = event.wait(1)
    if not started:
        raise TimeoutError("Starting of proxy server failed.")
    log.info("Proxy thread started.")
    return context


def main(
    arguments: Optional[list[str]] = None, stop_event: Optional[threading.Event] = None
) -> None:
    from pyleco.utils.parser import ArgumentParser, parse_command_line_parameters

    parser = ArgumentParser(prog="Proxy server")
    parser.add_argument(
        "-s", "--sub", help="set the host name to subscribe to", default="localhost"
    )
    parser.add_argument("-p", "--pub", help="set the host name to publish to", default="localhost")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase the logging level by one, may be used more than once",
    )
    parser.add_argument(
        "-c",
        "--captured",
        action="store_true",
        default=False,
        help="log all messages sent through the proxy",
    )
    parser.add_argument("-o", "--offset", help="shifting the port numbers.", default=0, type=int)
    kwargs = parse_command_line_parameters(
        parser=parser, logger=log, arguments=arguments, logging_default=logging.INFO
    )

    log.addHandler(logging.StreamHandler())
    if kwargs.get("captured"):
        log.setLevel(logging.DEBUG)
    merely_local = kwargs.get("pub") == "localhost" and kwargs.get("sub") == "localhost"

    if not merely_local:
        log.info(
            f"Remote proxy from {kwargs.get('sub', 'localhost')} "
            f"to {kwargs.get('pub', 'localhost')}."
        )
    else:
        log.info(
            "This data broker manages the data between measurement software, "
            f"which publishes on port {port}, and all the consumers of data "
            f" (DataLogger, Beamprofiler etc.), which subscribe on port {port - 1}."
        )
    context = zmq.Context()
    start_proxy(context=context, **kwargs)
    if merely_local:
        start_proxy(context=context, offset=1)  # for log entries
    reader = context.socket(zmq.SUB)
    reader.connect("inproc://capture")
    reader.subscribe(b"")
    poller = zmq.Poller()
    poller.register(reader, zmq.POLLIN)
    while stop_event is None or not stop_event.is_set():
        if socks := dict(poller.poll(1)):
            if reader in socks:
                received = reader.recv_multipart()
                log.debug(f"Message brokered: {received}")
    context.term()


if __name__ == "__main__":  # pragma: no cover
    main()
