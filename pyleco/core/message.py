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

from typing import List, Optional


from . import VERSION_B
from .serialization import (create_header_frame, serialize_data, interpret_header, split_name,
                            deserialize_data,
                            )


# Control transfer protocol
class Message:
    """A message in LECO protocol.

    It consists of the following bytes frames, for which each an attribute exists:
        - `version`
        - `receiver`
        - `sender`
        - `header`
        - 0 or more `payload` frames

    If you do not specify a sender, the sending program shall add it itself.
    The :attr:`data` attribute is the content of the first :attr:`payload` frame.
    All attributes, except the official frames, are for convenience.
    """

    version: bytes = VERSION_B

    def __init__(self, receiver: bytes | str, sender: bytes | str = b"", data: object = None,
                 header: Optional[bytes] = None, **kwargs) -> None:
        # setup caches
        self.receiver = receiver if isinstance(receiver, bytes) else receiver.encode()
        self.sender = sender if isinstance(sender, bytes) else sender.encode()
        self.header = create_header_frame(**kwargs) if header is None else header
        self._data = data
        self._payload: List[bytes] = []
        self._header_elements = None  # cache
        self._sender_elements = None  # cache
        self._receiver_elements = None  # cache

    @classmethod
    def from_frames(cls, version: bytes, receiver: bytes, sender: bytes, header: bytes,
                    *payload: bytes):
        """Create a message from a frames list, for example after reading from a socket.

        .. code::

            frames = socket.recv_multipart()
            message = Message.from_frames(*frames)
        """
        inst = cls(receiver, sender, header=header)
        inst.version = version
        inst.payload = list(payload)
        return inst

    def get_frames_list(self) -> List[bytes]:
        """Get a list representation of the message, ready for sending it."""
        if not self.sender:
            raise ValueError("Empty sender frame not allowed to send.")
        return self._get_frames_without_check()

    def _get_frames_without_check(self) -> List[bytes]:
        return [self.version, self.receiver, self.sender, self.header] + self.payload

    @property
    def receiver(self) -> bytes:
        return self._receiver

    @receiver.setter
    def receiver(self, value: bytes):
        self._receiver = value
        self._receiver_elements = None  # reset cache

    @property
    def sender(self) -> bytes:
        return self._sender

    @sender.setter
    def sender(self, value: bytes):
        self._sender = value
        self._sender_elements = None  # reset cache

    @property
    def header(self) -> bytes:
        return self._header

    @header.setter
    def header(self, value: bytes):
        self._header = value
        self._header_elements = None  # reset cache

    @property
    def payload(self) -> List[bytes]:
        if self._payload == [] and self._data is not None:
            self._payload = [serialize_data(self._data)]
        return self._payload

    @payload.setter
    def payload(self, value: List[bytes]) -> None:
        self._payload = value
        self._data = None  # reset data

    @property
    def conversation_id(self) -> bytes:
        if self._header_elements is None:
            self._header_elements = interpret_header(self.header)
        return self._header_elements[0]

    @property
    def message_id(self) -> bytes:
        if self._header_elements is None:
            self._header_elements = interpret_header(self.header)
        return self._header_elements[1]

    @property
    def receiver_node(self) -> bytes:
        if self._receiver_elements is None:
            self._receiver_elements = split_name(self.receiver)
        return self._receiver_elements[0]

    @property
    def receiver_name(self) -> bytes:
        if self._receiver_elements is None:
            self._receiver_elements = split_name(self.receiver)
        return self._receiver_elements[1]

    @property
    def sender_node(self) -> bytes:
        if self._sender_elements is None:
            self._sender_elements = split_name(self.sender)
        return self._sender_elements[0]

    @property
    def sender_name(self) -> bytes:
        if self._sender_elements is None:
            self._sender_elements = split_name(self.sender)
        return self._sender_elements[1]

    @property
    def data(self) -> object:
        if self._data is None and self.payload:
            self._data = deserialize_data(self.payload[0])
        return self._data

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        return (self.version == other.version and self.receiver == other.receiver
                and self.sender == other.sender and self.payload == other.payload)

    def __repr__(self) -> str:
        return f"Message.from_frames({self._get_frames_without_check()})"

    # String access properties
    @property
    def receiver_str(self) -> str:
        return self.receiver.decode()

    @receiver_str.setter
    def receiver_str(self, value: str):
        self.receiver = value.encode()

    @property
    def sender_str(self) -> str:
        return self.sender.decode()

    @sender_str.setter
    def sender_str(self, value: str):
        self.sender = value.encode()

    @property
    def receiver_node_str(self) -> str:
        return self.receiver_node.decode()

    @property
    def receiver_name_str(self) -> str:
        return self.receiver_name.decode()

    @property
    def sender_node_str(self) -> str:
        return self.sender_node.decode()

    @property
    def sender_name_str(self) -> str:
        return self.sender_name.decode()
