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
import datetime
from enum import IntEnum, IntFlag
import json
from typing import Any, Optional, NamedTuple, Union

# as long as uuid does not yet support UUIDv7 use uuid6
from uuid6 import uuid7
from ..json_utils.json_objects import (
    Request,
    ParamsRequest,
    ResultResponse,
    ErrorResponse,
    Notification,
    ParamsNotification,
)


json_objects = (
    Request,
    ParamsRequest,
    ResultResponse,
    ErrorResponse,
    Notification,
    ParamsNotification,
)


class FullName(NamedTuple):
    namespace: bytes
    name: bytes


class FullNameStr(NamedTuple):
    namespace: str
    name: str


class Header(NamedTuple):
    conversation_id: bytes
    message_id: bytes
    message_type: int


class MessageTypes(IntEnum):
    """The different message types, represented as an integer in the range [0, 255]."""
    NOT_DEFINED = 0
    JSON = 1


class JsonContentTypes(IntFlag):
    """Type of the JSON content."""
    INVALID = 0
    REQUEST = 1
    RESPONSE = 2
    RESULT = 4
    ERROR = 8
    BATCH = 16
    RESULT_RESPONSE = RESPONSE + RESULT
    ERROR_RESPONSE = RESPONSE + ERROR


def create_header_frame(conversation_id: Optional[bytes] = None,
                        message_id: Optional[Union[bytes, int]] = 0,
                        message_type: Union[bytes, int, MessageTypes] = MessageTypes.NOT_DEFINED,
                        ) -> bytes:
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
    elif isinstance(message_id, int):
        message_id = message_id.to_bytes(length=3, byteorder='big')
    elif len(message_id) != 3:
        raise ValueError("Length of 'message_id' is not 3 bytes.")
    if isinstance(message_type, int):
        message_type = message_type.to_bytes(length=1, byteorder="big")
    elif len(message_type) != 1:
        raise ValueError("Length of 'message_type' is not 1 bytes.")
    return b"".join((conversation_id, message_id, message_type))


def split_name(name: bytes, namespace: bytes = b"") -> FullName:
    """Split a sender/receiver name with given default namespace."""
    s = name.split(b".")
    n = s.pop(-1)
    return FullName((s.pop() if s else namespace), n)


def split_name_str(name: str, namespace: str = "") -> FullNameStr:
    """Split a sender/receiver name with given default namespace."""
    s = name.split(".")
    n = s.pop(-1)
    return FullNameStr((s.pop() if s else namespace), n)


def interpret_header(header: bytes) -> Header:
    """Interpret the header frame.

    :return: conversation_id, message_id, message_type
    """
    conversation_id = header[:16]
    message_id = header[16:19]
    message_type = int.from_bytes(header[19:20], byteorder="big")
    return Header(conversation_id, message_id, message_type)


def serialize_data(data: Any) -> bytes:
    """Turn `data` into a bytes object.

    Due to json serialization, data must not contain a bytes object!
    """
    if isinstance(data, json_objects):
        return data.model_dump_json().encode()  # type: ignore
    else:
        return json.dumps(data, separators=(',', ':')).encode()


def deserialize_data(content: bytes) -> Any:
    """Turn received message content into python objects."""
    return json.loads(content.decode())


def generate_conversation_id() -> bytes:
    """Generate a conversation_id."""
    return uuid7().bytes


def conversation_id_to_datetime(conversation_id: bytes) -> datetime.datetime:
    seconds_since_epoch = int.from_bytes(conversation_id[:6], byteorder="big", signed=False) / 1000
    return datetime.datetime.fromtimestamp(seconds_since_epoch, tz=datetime.timezone.utc)


def _get_json_object_type(data: dict[str, Any]) -> JsonContentTypes:
    if isinstance(data, dict):
        if "method" in data.keys():
            return JsonContentTypes.REQUEST
        elif "result" in data.keys():
            return JsonContentTypes.RESULT_RESPONSE
        elif "error" in data.keys():
            return JsonContentTypes.ERROR_RESPONSE
    return JsonContentTypes.INVALID


def get_json_content_type(data: Any) -> JsonContentTypes:
    if isinstance(data, list):
        content = JsonContentTypes.BATCH if data else JsonContentTypes.INVALID
        for element in data:
            element_typ = _get_json_object_type(element)
            if element_typ == JsonContentTypes.INVALID:
                return JsonContentTypes.INVALID
            else:
                content |= element_typ
        return content
    else:
        return _get_json_object_type(data)
