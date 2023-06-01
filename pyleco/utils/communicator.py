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

from abc import abstractmethod
import logging
from time import perf_counter
from typing import Protocol, Optional

import zmq

from ..core.message import Message
from ..core.enums import Commands, Errors
from ..core.serialization import generate_conversation_id, split_message


class Communicator(Protocol):
    """Definition of a Communicator."""

    name: str
    node: str | None = None

    # def __init__(
    #         self,
    #         name: str,
    #         host: str = "localhost",
    #         port: int = 12300,
    #         protocol: str = "tcp",
    #         **kwargs
    # ) -> None:
    #     self.name = name

    @abstractmethod
    def send(self, receiver: str | bytes,
             conversation_id: bytes = b"",
             data: object = None,
             **kwargs) -> None:
        """Send a message based on kwargs."""
        raise NotImplementedError

    @abstractmethod
    def send_message(self, message: Message) -> None:
        """Send a message."""
        raise NotImplementedError

    # implement?
    # @abstractmethod
    # def poll(self, timeout: float | None = 0) -> bool:
    #     """Check whether a message can be read."""
    #     raise NotImplementedError

    # @abstractmethod
    # def read(self) -> Message:
    #     """Read a message."""
    #     raise NotImplementedError

    @abstractmethod
    def ask(self, receiver: bytes | str, conversation_id: bytes = b"",
            data: object = None,
            **kwargs) -> Message:
        """Send a message based on kwargs and retrieve the response."""
        raise NotImplementedError

    @abstractmethod
    def ask_message(self, message: Message) -> Message:
        """Send a message and retrieve the response"""
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


class SimpleCommunicator(Communicator):
    """Sending requests via zmq and reading the answer.

    The communicator can be used in a context, which ensures sign-in and sign-out:

    .. code::

        with Communicator(name="test") as com:
            com.send("receiver")

    :param str host: Hostname
    :param int port: Port to connect to.
    :param str name: Name to send messages as.
    :param int timeout: Timeout in ms.
    :param bool auto_open: Open automatically a connection upon instantiation.
    :param str protocol: Protocol name to use.
    :param bool standalone: Whether to bind to the port in standalone mode.
    """

    def __init__(
        self,
        name: str,
        host="localhost",
        port: Optional[int] = 12300,
        timeout=100,
        auto_open=True,
        protocol="tcp",
        standalone=False,
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
        self.node = None
        self._last_beat = 0
        self._reading = None
        super().__init__(**kwargs)

    def open(self) -> None:
        """Open the connection."""
        context = zmq.Context.instance()
        self.connection = context.socket(zmq.DEALER)
        protocol, standalone = self._conn_details
        if standalone:
            self.connection.bind(f"{protocol}://*:{self.port}")
        else:
            self.connection.connect(f"{protocol}://{self.host}:{self.port}")

    def close(self) -> None:
        """Close the connection."""
        try:
            self.sign_out()
            self.connection.close(1)
        except (AttributeError, TimeoutError):
            pass

    def reset(self) -> None:
        """Reset socket"""
        self.close()
        self.open()

    def __del__(self) -> None:
        self.close()

    def __enter__(self):
        """Called with `with` keyword, returns the Director."""
        if not hasattr(self, "connection"):
            self.open()
        self.sign_in()
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        """Called after the with clause has finished, does cleanup."""
        self.close()

    def retry_read(self, timeout=None):
        """Retry reading."""
        if self._reading and self.connection.poll(timeout or self.timeout):
            return self._reading()
            self._reading = None

    def send_message(self, message: Message) -> None:
        now = perf_counter()
        if now > self._last_beat + 15:
            self.sign_in()
        self._last_beat = now
        if not message.sender:
            message.sender = (".".join((self.node, self.name)) if self.node else self.name).encode()
        frames = message.get_frames_list()
        self.connection.send_multipart(frames)

    def send(self, receiver: str | bytes, conversation_id=b"", data=None,
             **kwargs) -> None:
        """Send an `data` object. No node check."""
        if isinstance(receiver, str):
            receiver = receiver.encode()
        msg = Message(
            receiver=receiver,
            conversation_id=conversation_id,
            data=data,
            **kwargs,
        )
        self.send_message(message=msg)

    def read_raw(self, timeout=None) -> list:
        if self.connection.poll(timeout or self.timeout):
            return self.connection.recv_multipart()
        else:
            self._reading = self.connection.recv_multipart
            raise TimeoutError("Reading timed out.")

    def poll(self) -> bool:
        """Check how many messages arrived."""
        return self.connection.poll()

    def read(self) -> Message:
        return Message.from_frames(*self.read_raw())

    def ask_raw(self, message: Message) -> Message:
        """Send and read the answer, without error checking."""
        self.send_message(message=message)
        while True:
            response = self.read()
            if response.data == [[Commands.PING]]:
                continue
            elif response.data == [[Commands.ERROR, Errors.NOT_SIGNED_IN]]:
                self.sign_in()
                self.send_message(message=message)
                continue
            return response

    def ask_message(self, message: Message) -> Message:
        response = self.ask_raw(message=message)
        if (response.sender_name == b"COORDINATOR"
                and response.data
                and response.data[0][0] == Commands.ERROR):
            raise ConnectionError(
                "CommunicationError, Coordinator response.", " ".join(response.data[0][1:])
            )
        return response

    def ask(self, receiver: str | bytes, conversation_id=b"", data=None, **kwargs) -> Message:
        """Send and read the answer, including error checking.

        :return: receiver, sender, conversation_id, message_id, data
        :raises ConnectionError: Second argument is the Coordinator response.
        """
        if isinstance(receiver, str):
            receiver = receiver.encode()
        message = Message(receiver=receiver, conversation_id=conversation_id, data=data, **kwargs)
        return self.ask_message(message=message)

    # Messages
    def sign_in(self) -> str:
        """Sign in to the Coordinator and return the node."""
        self.node = None
        cid0 = generate_conversation_id()
        self._last_beat = perf_counter()  # to not sign in again...
        request = Message(receiver=b"COORDINATOR", data=[[Commands.SIGNIN]], conversation_id=cid0)
        response = self.ask_raw(message=request)
        assert (
            response.conversation_id == cid0
        ), (f"Answer to another request (mine {cid0}) received from {response.sender}: "
            f"{response.conversation_id}, {response.data}.")
        self.node = response.sender_node.decode()
        return self.node

    def heartbeat(self) -> None:
        """Send a heartbeat to the connected Coordinator."""
        self.send_message(message=Message(receiver=b"COORDINATOR"))

    def sign_out(self) -> None:
        """Tell the Coordinator to drop references."""
        self.ask_message(message=Message(receiver=b"COORDINATOR", data=[[Commands.SIGNOUT]]))

    # backward compatibility
    def retrieve_header_and_data(self, message: Message) -> tuple:
        return split_message(msg_frames=message.get_frames_list())
