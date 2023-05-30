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
    from enum import StrEnum  # type: ignore
except ImportError:
    # for versions <3.11
    from enum import Enum

    class StrEnum(str, Enum):
        pass  # just inherit
import json
import random
import struct
from time import time


# Current protocol version
VERSION = 0
VERSION_B = VERSION.to_bytes(1, "big")


# Control transfer protocol
class Message:
    """A message in LECO protocol.

    It consists of the following frames, for which each an attribute exists:
        version
        receiver
        sender
        header
        0 or more payload frames

    If you do not specify a sender, the sending program shall add it itself.
    The :attr:`data` attribute is the content of the first payload frame.
    All attributes, except the official frames, are for convenience.
    """

    version: bytes = VERSION_B

    def __init__(self, receiver: bytes, sender: bytes = b"", data=None,
                 header: None | bytes = None, **kwargs) -> None:
        # setup caches
        self.receiver = receiver
        self.sender = sender
        self.header = create_header_frame(**kwargs) if header is None else header
        self._data = data
        self._payload = []
        self._header_elements = None  # cache
        self._sender_elements = None  # cache
        self._receiver_elements = None  # cache

    @classmethod
    def from_frames(cls, version: bytes, receiver: bytes, sender: bytes, header: bytes,
                    *payload):
        """Create a message from a frames list, for example after reading from a socket."""
        inst = cls(receiver, sender, header=header)
        inst.version = version
        inst.payload = list(payload)
        return inst

    @classmethod
    def create_message_with_conversion(cls, receiver: bytes | str, sender: bytes | str,
                                       data: object = None, **kwargs):
        if isinstance(receiver, str):
            receiver = receiver.encode()
        if isinstance(sender, str):
            sender = sender.encode()
        return cls(receiver, sender, data=data, **kwargs)

    def get_frames_list(self) -> list:
        """Get a list representation of the message, ready for sending it."""
        if self.sender == b"":
            raise ValueError("Empty sender frame not allowed to send.")
        return self._get_frames_without_check()

    def _get_frames_without_check(self):
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
    def payload(self) -> list:
        if self._payload == [] and self._data is not None:
            self._payload = [serialize_data(self._data)]
        return self._payload

    @payload.setter
    def payload(self, value: list) -> None:
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

    def __eq__(self, other):
        return (self.version == other.version and self.receiver == other.receiver
                and self.sender == other.sender and self.payload == other.payload)

    def __repr__(self):
        return f"Message.from_frames({self._get_frames_without_check()})"


def create_header_frame(conversation_id: bytes = b"", message_id: bytes = b"") -> bytes:
    """Create the header frame.

    :param bytes conversation_id: ID of the conversation.
    :param bytes message_id: Message ID of this message, must not contain ";".
    :return: header frame.
    """
    return b";".join((conversation_id, message_id))


def create_message(receiver: bytes, sender: bytes = b"", payload: bytes | list | None = None,
                   **kwargs) -> list:
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
    """Return version, receiver, sender, header frame, and payload frames of a message."""
    return msg[0], msg[1], msg[2], msg[3], msg[4:]


def split_name(name: bytes, node: bytes = b""):
    """Split a sender/receiver name with given default node."""
    s = name.split(b".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def split_name_str(name: str, node: str = ""):
    """Split a sender/receiver name with given default node."""
    s = name.split(".")
    n = s.pop(-1)
    return (s.pop() if s else node), n


def interpret_header(header: bytes):
    """Interpret the header frame.

    :return: conversation_id, message_id
    """
    try:
        conversation_id, message_id = header.rsplit(b";", maxsplit=1)
    except (IndexError, ValueError):
        conversation_id = b""
        message_id = b""
    return conversation_id, message_id


# Control content protocol
class Commands(StrEnum):
    """Valid commands for the control protocol."""

    # Coordinator communication requests
    SIGNIN = "SI"
    SIGNOUT = "D"
    CO_SIGNIN = "COS"  # Sign in as a Coordinator
    CO_SIGNOUT = "COD"
    PING = "P"  # Ping: Check, whether the other side is alive.
    # Component communication requests
    GET = "G"
    SET = "S"
    CALL = "C"
    OFF = "O"  # Turn off program
    CLEAR = "X"
    LOG = "L"  # configure log level
    LIST = "?"  # List options
    SAVE = "V"
    # Responses
    ACKNOWLEDGE = "A"  # Message received. Response is appended.
    ERROR = "E"  # An error occurred.
    # Deprecated
    DISCONNECT = "D"  # Deprecated, use SIGNOUT instead


class Errors(StrEnum):
    """Error messages for the control protocol."""

    # Routing errors (Coordinator)
    NOT_SIGNED_IN = "You did not sign in!"
    DUPLICATE_NAME = "The name is already taken."
    NODE_UNKNOWN = "Node is not known."
    RECEIVER_UNKNOWN = "Receiver is not in addresses list."
    # Data errors (Actors)
    NAME_NOT_FOUND = "The requested name is not known."  # name of a property or method.
    EXECUTION_FAILED = "Execution of the action failed."


class CommunicationError(ConnectionError):
    """Something went wrong, send a `error_msg` to the recipient."""
    def __init__(self, text: str, error_payload, *args: object) -> None:
        super().__init__(text, *args)
        self.error_payload = error_payload


def serialize_data(data: object) -> bytes:
    """Turn data into a bytes object."""
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
                    conversation_id: bytes | str = b"", message_id: bytes | str = b"", data=None):
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
    return create_message(receiver, sender, payload=data, conversation_id=conversation_id,
                          message_id=message_id)


def split_message(msg):
    """Split the recieved message and return strings and the data object.

    :return: receiver, sender, conversation_id, message_id, data
    """
    # Store necessary data like address and maybe conversation ID
    version, receiver, sender, header, payload = divide_message(msg)
    assert (v := int.from_bytes(version, "big")) <= VERSION, (
        f"Version {v} is above current version {VERSION}.")
    conversation_id, message_id = interpret_header(header)
    data = deserialize_data(payload[0]) if payload else None
    return receiver.decode(), sender.decode(), conversation_id, message_id, data


# For tests
class FakeContext:
    """A fake context instance, similar to the result of `zmq.Context.instance()."""

    def socket(self, socket_type):
        return FakeSocket(socket_type)


class FakeSocket:
    """A fake socket mirroring zmq.socket API, useful for unit tests.

    :attr list _s: contains a list of messages sent via this socket.
    :attr list _r: List of messages which can be read.
    """

    def __init__(self, socket_type, *args):
        self.socket_type = socket_type
        self.addr = None
        self._s = []
        self._r = []
        self.closed = False

    def bind(self, addr):
        self.addr = addr

    def bind_to_random_port(self, addr, *args, **kwargs):
        self.addr = addr
        return 5

    def unbind(self, addr=None):
        self.addr = None

    def connect(self, addr):
        self.addr = addr

    def disconnect(self, addr=None):
        self.addr = None

    def poll(self, timeout=0, flags="PollEvent.POLLIN"):
        return 1 if len(self._r) else 0

    def recv_multipart(self):
        return self._r.pop()

    def send_multipart(self, parts):
        print(parts)
        for i, part in enumerate(parts):
            if not isinstance(part, bytes):
                # Similar to real error message.
                raise TypeError(f"Frame {i} ({part}) does not support the buffer interface.")
        self._s.append(list(parts))

    def close(self, linger=None):
        self.addr = None
        self.closed = True
