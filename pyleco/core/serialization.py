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

import json
from typing import Optional, NamedTuple

from uuid_extensions import uuid7  # as long as uuid does not yet support UUIDv7
from jsonrpcobjects.objects import (RequestObject, RequestObjectParams,
                                    ResultResponseObject,
                                    ErrorResponseObject,
                                    NotificationObject, NotificationObjectParams,
                                    )


json_objects = (
    RequestObject,
    RequestObjectParams,
    ResultResponseObject,
    ErrorResponseObject,
    NotificationObject,
    NotificationObjectParams,
)


class FullName(NamedTuple):
    namespace: bytes
    name: bytes


class Header(NamedTuple):
    conversation_id: bytes
    message_id: bytes
    message_type: bytes


def create_header_frame(conversation_id: Optional[bytes] = None,
                        message_id: Optional[bytes] = None,
                        message_type: Optional[bytes] = None) -> bytes:
    """Create the header frame.

    :param bytes conversation_id: ID of the conversation.
    :param bytes message_id: Message ID of this message.
    :return: header frame.
    """
    if conversation_id is None:
        conversation_id = generate_conversation_id()
    elif (length := len(conversation_id)) != 16:
        raise ValueError(f"Length of 'conversation_id' is {length}, not 16 bytes.")
    if message_id is None:
        message_id = b"\x00" * 3
    elif len(message_id) != 3:
        raise ValueError("Length of 'message_id' is not 3 bytes.")
    if message_type is None:
        message_type = b"\x00"
    elif len(message_type) != 1:
        raise ValueError("Length of 'message_type' is not 1 bytes.")
    return b"".join((conversation_id, message_id, message_type))


def split_name(name: bytes, node: bytes = b"") -> FullName:
    """Split a sender/receiver name with given default node."""
    s = name.split(b".")
    n = s.pop(-1)
    return FullName((s.pop() if s else node), n)


def split_name_str(name: str, node: str = "") -> tuple[str, str]:
    """Split a sender/receiver name with given default node."""
    s = name.split(".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def interpret_header(header: bytes) -> Header:
    """Interpret the header frame.

    :return: conversation_id, message_id, message_type
    """
    conversation_id = header[:16]
    message_id = header[16:19]
    message_type = header[19:20]
    return Header(conversation_id, message_id, message_type)


def serialize_data(data: object) -> bytes:
    """Turn `data` into a bytes object.

    Due to json serialization, data must not contain a bytes object!
    """
    if isinstance(data, json_objects):
        return data.json().encode()  # type: ignore
    else:
        return json.dumps(data).encode()


def deserialize_data(content: bytes) -> object:
    """Turn received message content into python objects."""
    return json.loads(content.decode())


def generate_conversation_id() -> bytes:
    """Generate a conversation_id."""
    return uuid7(as_type="bytes")  # type: ignore
