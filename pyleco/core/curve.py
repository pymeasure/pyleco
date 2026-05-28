#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

from pyleco.core.security import KeyPair

if TYPE_CHECKING:
    import zmq

__all__ = [
    "configure_curve_server",
    "configure_curve_client",
    "warn_insecure_mode",
]


def configure_curve_server(socket: zmq.Socket, server_key_pair: KeyPair) -> None:
    socket.curve_server = True
    socket.curve_secretkey = server_key_pair.secret_key.encode()


def configure_curve_client(
    socket: zmq.Socket, client_key_pair: KeyPair, server_public_key: str
) -> None:
    socket.curve_serverkey = server_public_key.encode()
    socket.curve_publickey = client_key_pair.public_key.encode()
    socket.curve_secretkey = client_key_pair.secret_key.encode()


def warn_insecure_mode(address: str | None = None, stacklevel: int = 3) -> None:
    if address is None:
        return
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    host = address.rsplit(":", 1)[0] if ":" in address else address
    host = host.strip("[]")
    if host not in loopback_hosts:
        warnings.warn(
            "NONE security mode on non-loopback interface is insecure",
            UserWarning,
            stacklevel=stacklevel,
        )
