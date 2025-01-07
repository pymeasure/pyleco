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
from json import JSONDecodeError
from typing import Any, Iterable, Optional, Union


from . import VERSION_B
from .serialization import (create_header_frame, serialize_data, interpret_header, split_name,
                            deserialize_data, FullName, Header, MessageTypes,
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
    The :attr:`data` attribute is the content of the first :attr:`payload` frame. It can be set with
    the corresponding argument.
    All attributes, except the official frames, are for convenience.
    """

    version: bytes = VERSION_B
    receiver: bytes
    sender: bytes
    header: bytes
    payload: list[bytes]

    def __init__(self,
                 receiver: Union[bytes, str],
                 sender: Union[bytes, str] = b"",
                 data: Optional[Union[bytes, str, Any]] = None,
                 header: Optional[bytes] = None,
                 conversation_id: Optional[bytes] = None,
                 message_id: Optional[bytes] = None,
                 message_type: Union[MessageTypes, int] = MessageTypes.NOT_DEFINED,
                 additional_payload: Optional[Iterable[bytes]] = None,
                 ) -> None:
        self.receiver = receiver.encode() if isinstance(receiver, str) else receiver
        self.sender = sender.encode() if isinstance(sender, str) else sender
        if header and (conversation_id or message_id or message_type != MessageTypes.NOT_DEFINED):
            raise ValueError(
                "You may not specify the header and some header element at the same time!")
        self.header = (create_header_frame(conversation_id=conversation_id, message_id=message_id,
                                           message_type=message_type)
                       if header is None else header)
        if isinstance(data, bytes):
            self.payload = [data]
        elif isinstance(data, str):
            self.payload = [data.encode()]
        elif data is None:
            self.payload = []
        else:
            self.payload = [serialize_data(data)]
        if additional_payload is not None:
            self.payload.extend(additional_payload)

    @classmethod
    def from_frames(cls, version: bytes, receiver: bytes, sender: bytes, header: bytes,
                    *payload: bytes):  # -> typing.Self for py>=3.11
        """Create a message from a frames list, for example after reading from a socket.

        .. code::

            frames = socket.recv_multipart()
            message = Message.from_frames(*frames)
        """
        inst = cls(receiver, sender, header=header, additional_payload=payload)
        inst.version = version
        return inst

    def to_frames(self) -> list[bytes]:
        """Get a list representation of the message, ready for sending it."""
        if not self.sender:
            raise ValueError("Empty sender frame not allowed to send.")
        return self._to_frames_without_sender_check()

    def _to_frames_without_sender_check(self) -> list[bytes]:
        return [self.version, self.receiver, self.sender, self.header] + self.payload

    # Convenience methods to access elements
    @property
    def receiver_elements(self) -> FullName:
        return split_name(self.receiver)

    @property
    def sender_elements(self) -> FullName:
        return split_name(self.sender)

    @property
    def header_elements(self) -> Header:
        return interpret_header(self.header)

    @property
    def conversation_id(self) -> bytes:
        return self.header_elements.conversation_id

    @property
    def data(self) -> object:
        return deserialize_data(self.payload[0]) if self.payload else None

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Message):
            return NotImplemented
        partial_comparison = (
            self.version == other.version
            and self.receiver == other.receiver
            and self.sender == other.sender
            and self.header == other.header
        )
        try:
            # Try to compare the data (python objects) instead of their bytes representation.
            my_data = self.data
            other_data = other.data
        except JSONDecodeError:
            # Maybe the payload is binary, compare the raw payload
            return partial_comparison and self.payload == other.payload
        else:
            return (partial_comparison and my_data == other_data
                    and self.payload[1:] == other.payload[1:])

    def __repr__(self) -> str:
        list_of_frames_strings = [
            str(frame) for frame in self._to_frames_without_sender_check()]
        return f"Message.from_frames({', '.join(list_of_frames_strings)})"
