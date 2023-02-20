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

try:
    from enum import StrEnum
except ImportError:
    # for versions <3.11
    from enum import Enum

    class StrEnum(str, Enum):
        pass  # just inherit
import json


# Current protocol version
VERSION = 0
VERSION_B = VERSION.to_bytes(1, "big")


# Control transfer protocol
def create_header_frame(conversation_id=b"", message_id=b""):
    """Create the header frame.

    :param bytes conversation_id: Message ID of the receiver, for example the ID of its request.
    :param bytes message_id: Message ID of this message.
    :return: header frame.
    """
    return b";".join((conversation_id, message_id))


def create_message(receiver, sender=b"", payload=None, **kwargs):
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


def divide_message(msg):
    """Return version, receiver, sender, header frame, and payload frames of a message"""
    return msg[0], msg[1], msg[2], msg[3], msg[4:]


def split_name(name, node=b""):
    """Split a sender/receiver name with given default node."""
    s = name.split(b".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def split_name_str(name, node=""):
    """Split a sender/receiver name with given default node."""
    s = name.split(".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def interpret_header(header):
    """Interpret the header frame."""
    try:
        conversation_id, message_id = header.split(b";")
    except (IndexError, ValueError):
        conversation_id = b""
        message_id = b""
    return conversation_id, message_id


# Control content protocol
class Commands(StrEnum):
    """Valid commands for the control protocol"""
    ERROR = "E"  # An error occurred.
    GET = "G"
    SET = "S"
    ACKNOWLEDGE = "A"  # Message received. Response is appended.
    CALL = "C"
    OFF = "O"  # Turn off program
    CLEAR = "X"
    SIGNIN = "SI"
    SIGNOUT = "D"
    LOG = "L"  # configure log level
    LIST = "?"  # List options
    SAVE = "V"
    CO_SIGNIN = "COS"  # Sign in as a Coordinator
    PING = "P"  # Ping: Check, whether the other side is alive.


def serialize_data(data):
    """Turn data into a bytes object."""
    return json.dumps(data).encode()


def deserialize_data(content):
    """Turn received message content into python objects."""
    return json.loads(content.decode())


# Convenience methods
def compose_message(receiver, sender="", conversation_id="", message_id="",
                    data=None,
                    ):
    """Compose a message.

    :param str/bytes receiver: To whom the message is going to be sent.
    :param str/bytes sender: Name of the sender of the message.
    :param str/bytes conversation_id: Conversation ID of the receiver, for example the ID of its request.
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
    return create_message(receiver, sender, payload=data, conversation_id=conversation_id, message_id=message_id)


def split_message(msg):
    """Split the recieved message and return strings and the data object.

    :return: receiver, sender, conversation_id, message_id, data
    """
    # Store necessary data like address and maybe conversation ID
    version, receiver, sender, header, payload = divide_message(msg)
    assert (v := int.from_bytes(version, "big")) <= VERSION, f"Version {v} is above current version {VERSION}."
    conversation_id, message_id = interpret_header(header)
    data = deserialize_data(payload[0]) if payload else None
    return receiver.decode(), sender.decode(), conversation_id.decode(), message_id.decode(), data


# For tests
class FakeContext:
    """A fake context instance, similar to the result of `zmq.Context.instance()."""

    def socket(self, socket_type):
        return FakeSocket(socket_type)


class FakeSocket:
    """A fake socket useful for unit tests.

    :attr list _s: contains a list of messages sent via this socket.
    :attr list _r: List of messages which can be read.
    """

    def __init__(self, socket_type, *args):
        self.socket_type = socket_type
        self.addr = None
        self._s = []
        self._r = []

    def bind(self, addr, *args):
        self.addr = addr

    def bind_to_random_port(self, addr, *args, **kwargs):
        self.addr = addr
        return 5

    def unbind(self, linger=0):
        self.addr = None

    def connect(self, addr, *args):
        self.addr = addr

    def disconnect(self, linger=0):
        self.addr = None

    def poll(self, timeout=0):
        return len(self._r)

    def recv_multipart(self):
        return self._r.pop()

    def send_multipart(self, parts):
        print(parts)
        self._s.append(list(parts))

    def close(self, *args):
        self.addr = None
