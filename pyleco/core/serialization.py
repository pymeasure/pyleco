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
import random
from time import time
import struct
from typing import List, Tuple, Optional

from . import VERSION, VERSION_B


def create_header_frame(conversation_id: bytes = b"", message_id: bytes = b"") -> bytes:
    """Create the header frame.

    :param bytes conversation_id: ID of the conversation.
    :param bytes message_id: Message ID of this message, must not contain ";".
    :return: header frame.
    """
    return b";".join((conversation_id, message_id))


def create_message(receiver: bytes, sender: bytes = b"",
                   payload: Optional[bytes | List[bytes]] = None,
                   **kwargs: bytes) -> List[bytes]:
    """Create a message.

    :param bytes receiver: To whom the message is going to be sent.
    :param bytes sender: Name of the sender of the message.
    :param list of bytes payload: Payload frames.
    :param \\**kwargs: Keyword arguments for the header creation.
    :return: list of byte messages, ready to send as frames.
    """
    if payload:
        if isinstance(payload, bytes):
            payload = [payload]
        return [VERSION_B, receiver, sender, create_header_frame(**kwargs)] + payload
    else:
        return [VERSION_B, receiver, sender, create_header_frame(**kwargs)]


def divide_message(msg_frames: List[bytes]) -> tuple[bytes, bytes, bytes, bytes, List[bytes]]:
    """Return version, receiver, sender, header frame, and payload frames of a message."""
    return msg_frames[0], msg_frames[1], msg_frames[2], msg_frames[3], msg_frames[4:]


def split_name(name: bytes, node: bytes = b"") -> Tuple[bytes, bytes]:
    """Split a sender/receiver name with given default node."""
    s = name.split(b".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def split_name_str(name: str, node: str = "") -> Tuple[str, str]:
    """Split a sender/receiver name with given default node."""
    s = name.split(".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def interpret_header(header: bytes) -> Tuple[bytes, bytes]:
    """Interpret the header frame.

    :return: conversation_id, message_id
    """
    try:
        conversation_id, message_id = header.rsplit(b";", maxsplit=1)
    except (IndexError, ValueError):
        conversation_id = b""
        message_id = b""
    return conversation_id, message_id


def serialize_data(data: object) -> bytes:
    """Turn `data` into a bytes object.

    Due to json serialization, data must not contain a bytes object!
    """
    return json.dumps(data).encode()


def deserialize_data(content: bytes) -> object:
    """Turn received message content into python objects."""
    return json.loads(content.decode())


def generate_conversation_id() -> bytes:
    """Generate a conversation_id."""
    # struct.pack uses 8 bytes and takes 0.1 seconds for 1 Million repetitions.
    # str().encode() uses 14 bytes and takes 0.5 seconds for 1 Million repetitions.
    # !d is a double (8 bytes) in network byte order (big-endian)
    return struct.pack("!d", time()) + random.randbytes(2)


# Convenience methods
def compose_message(receiver: bytes | str, sender: bytes | str = "",
                    conversation_id: bytes | str = b"", message_id: bytes | str = b"",
                    data: object = None) -> List[bytes]:
    """Compose a message.

    :param str/bytes receiver: To whom the message is going to be sent.
    :param str/bytes sender: Name of the sender of the message.
    :param str/bytes conversation_id: Conversation ID of the receiver,
        for example the ID of its request.
    :param str/bytes message_id: Message ID of this message.
    :param data: Python object to send or bytes object.
    :return: list of byte messages, sent as frames.
    """
    if isinstance(receiver, str):
        receiver = receiver.encode()
    if isinstance(sender, str):
        sender = sender.encode()
    if isinstance(conversation_id, str):
        conversation_id = conversation_id.encode()
    if isinstance(message_id, str):
        message_id = message_id.encode()

    if data is not None and not isinstance(data, bytes):
        data = serialize_data(data)
    return create_message(receiver=receiver, sender=sender, payload=data,
                          conversation_id=conversation_id,
                          message_id=message_id)


def split_message(msg_frames: List[bytes]) -> Tuple[str, str, bytes, bytes, object]:
    """Split the recieved message and return strings and the data object.

    :return: receiver, sender, conversation_id, message_id, data
    """
    # Store necessary data like address and maybe conversation ID
    version, receiver, sender, header, payload = divide_message(msg_frames=msg_frames)
    assert (v := int.from_bytes(version, byteorder="big")) <= VERSION, (
        f"Version {v} is above current version {VERSION}.")
    conversation_id, message_id = interpret_header(header)
    data = deserialize_data(content=payload[0]) if payload else None
    return receiver.decode(), sender.decode(), conversation_id, message_id, data
