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

from __future__ import annotations
import logging
from time import perf_counter
from typing import Optional, Union

import zmq

from ..core import COORDINATOR_PORT
from ..core.message import Message, MessageTypes
from ..json_utils.rpc_generator import RPCGenerator
from ..json_utils.errors import NOT_SIGNED_IN
from .base_communicator import BaseCommunicator


class Communicator(BaseCommunicator):
    """A simple Communicator, which sends requests and reads the answer.

    This Communicator does not listen for incoming messages. It only handles messages, whenever
    you try to read one. It is intended for sending messages and reading the answer without
    implementing threading.

    The communicator can be used in a context, which ensures sign-in and sign-out:

    .. code::

        with Communicator(name="test") as com:
            com.send("receiver")

    :param str host: Hostname
    :param int port: Port to connect to.
    :param str name: Name to send messages as.
    :param int timeout: Timeout in s.
    :param bool auto_open: Open automatically a connection upon instantiation.
    :param str protocol: Protocol name to use.
    :param bool standalone: Whether to bind to the port in standalone mode.
    """

    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Optional[int] = COORDINATOR_PORT,
        timeout: float = 0.1,
        auto_open: bool = True,
        protocol: str = "tcp",
        standalone: bool = False,
        **kwargs,
    ) -> None:
        self.log = logging.getLogger(f"{__name__}.Communicator")
        self.host = host
        self.port = port
        self._conn_details = protocol, standalone
        self.timeout = timeout
        self.log.info(f"Communicator initialized on {host}:{port}.")
        if auto_open:
            self.open()
        self.name = name
        self.namespace = None
        self._last_beat: float = 0
        self.rpc_generator = RPCGenerator()
        super().__init__(**kwargs)
        self.setup_message_buffer()

    def open(self, context: Optional[zmq.Context] = None) -> None:
        """Open the connection."""
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.DEALER)
        protocol, standalone = self._conn_details
        if standalone:
            self.socket.bind(f"{protocol}://*:{self.port}")
        else:
            self.socket.connect(f"{protocol}://{self.host}:{self.port}")

    def close(self) -> None:
        """Close the connection."""
        if (not hasattr(self, "socket")) or self.socket.closed:
            return
        try:
            self.sign_out()
        except TimeoutError:
            self.log.warning("Closing, the sign out failed with a timeout.")
        except ConnectionRefusedError:
            self.log.warning("Closing, the sign out failed with a refused connection.")
        finally:
            super().close()

    def reset(self) -> None:
        """Reset socket"""
        self.close()
        self.open()

    def __del__(self) -> None:
        self.close()

    def __enter__(self):  # -> typing.Self for py>=3.11
        """Called with `with` keyword, returns the Director."""
        if not hasattr(self, "socket"):
            self.open()
        self.sign_in()
        return self

    def send_message(self, message: Message) -> None:
        now = perf_counter()
        if now > self._last_beat + 15 and message.payload and b"sign_in" not in message.payload[0]:
            self.sign_in()
        self._last_beat = now
        super().send_message(message=message)

    def poll(self, timeout: Optional[float] = None) -> int:
        """Check how many messages arrived."""
        if timeout is None:
            timeout = self.timeout
        return self.socket.poll(timeout=int(timeout * 1000))  # in ms

    def handle_not_signed_in(self):
        super().handle_not_signed_in()
        raise ConnectionResetError("Have not been signed in, signing in.")

    def ask_message(self, message: Message, timeout: Optional[float] = None) -> Message:
        """Send and read the answer, signing in if necessary."""
        for _ in range(2):
            try:
                return super().ask_message(message=message, timeout=timeout)
            except ConnectionResetError:
                pass  # sign in required, retry
        raise ConnectionRefusedError(NOT_SIGNED_IN.message)

    def ask_json(self, receiver: Union[bytes, str], json_string: str,
                 timeout: Optional[float] = None
                 ) -> bytes:
        message = Message(receiver=receiver, data=json_string, message_type=MessageTypes.JSON)
        response = self.ask_message(message=message, timeout=timeout)
        return response.payload[0]

    # Messages
    def sign_in(self) -> None:
        """Sign in to the Coordinator and return the node."""
        self._last_beat = perf_counter()  # to not sign in again...
        super().sign_in()
        if self.namespace is None:
            raise ConnectionRefusedError("Sign in failed.")

    def get_capabilities(self, receiver: Union[bytes, str]) -> dict:
        return self.ask_rpc(receiver=receiver, method="rpc.discover")
