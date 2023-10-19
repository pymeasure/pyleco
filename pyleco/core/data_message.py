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

from json import JSONDecodeError
from typing import Any

from .serialization import deserialize_data, generate_conversation_id, serialize_data


class DataMessage:
    """A message of the data protocol."""

    topic: bytes
    header: bytes
    payload: list[bytes]

    def __init__(self,
                 topic: bytes | str,
                 header: bytes | None = None,
                 data: bytes | str | Any | None = None,
                 conversation_id: bytes | None = None,
                 message_type: int | None = None,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        self.topic = topic.encode() if isinstance(topic, str) else topic
        if header and (conversation_id or message_type is not None):
            raise ValueError(
                "You may not specify the header and some header element at the same time!")
        if header is None:
            cid = generate_conversation_id() if conversation_id is None else conversation_id
            self.header = cid + bytes(message_type or 0)
        else:
            self.header = header
        if isinstance(data, bytes):
            self.payload = [data]
        elif isinstance(data, str):
            self.payload = [data.encode()]
        elif data is None:
            self.payload = []
        else:
            self.payload = [serialize_data(data)]

    @classmethod
    def from_frames(cls, topic: bytes, header: bytes, *payload: bytes):
        """Create a message from a frames list, for example after reading from a socket.

        .. code::

            frames = socket.recv_multipart()
            message = DataMessage.from_frames(*frames)
        """
        message = cls(topic=topic, header=header)
        message.payload = list(payload)
        return message

    def to_frames(self) -> list[bytes]:
        return [self.topic, self.header] + self.payload

    @property
    def conversation_id(self) -> bytes:
        return self.header[:-1]

    @property
    def message_type(self) -> int:
        return self.header[-1]

    @property
    def data(self) -> object:
        return deserialize_data(self.payload[0]) if self.payload else None

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, DataMessage):
            return NotImplemented
        partial_comparison = (
            self.topic == other.topic
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
        return f"DataMessage.from_frames({self.to_frames()})"


class LogMessage(DataMessage):
    """A message of the data protocol to transmit log entries."""

    def __init__(self,
                 topic: bytes | str,
                 log_message: str,
                 **kwargs) -> None:
        super().__init__(topic=topic, data=log_message.encode(), **kwargs)
