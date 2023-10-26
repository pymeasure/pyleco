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

import pytest

from pyleco.core import VERSION_B

from pyleco.core.message import Message, MessageTypes
from pyleco.core.internal_protocols import CommunicatorProtocol
from pyleco.utils.pipe_handler import PipeHandler, MessageBuffer

from pyleco.utils.listener import Listener


cid = b"conversation_id;"  # conversation_id
header = b"".join((cid, b"mid", b"\x00"))
# the result
msg = Message(b"r", b"s", conversation_id=cid, message_id=b"mid")
msg_list = ("r", "s", cid, b"", None)
# some different message
other = Message(b"r", b"s", conversation_id=b"conversation_id9", message_id=b"mid")


class FakeHandler(PipeHandler):

    def __init__(self, received: list[Message] | None = None) -> None:
        self._sent: list[Message] = []
        self._received: list[Message] = received or []
        self.buffer = MessageBuffer()
        self.full_name = "N.Pipe"

    def pipe_setup(self, context=None) -> None:  # type: ignore[override]
        pass

    def pipe_send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.full_name.encode()
        self._sent.append(message)

    def pipe_read_message(self, conversation_id: bytes, tries: int = 10, timeout: float = 0.1
                          ) -> Message:
        return self._received.pop(0)


@pytest.fixture
def listener() -> Listener:
    listener = Listener(name="test")  # type: ignore
    listener.message_handler = FakeHandler()
    return listener


def static_test_listener_is_communicator():
    def testing(listener: CommunicatorProtocol):
        pass
    testing(Listener(name="listener"))


def test_send(listener: Listener):
    listener.send(receiver="N2.CB", conversation_id=cid, message_id=b"mid", data=[["TEST"]])
    assert listener.message_handler._sent == [  # type: ignore
        Message.from_frames(VERSION_B, b"N2.CB", b"N.Pipe", header, b'[["TEST"]]')]


@pytest.mark.parametrize("buffer", ([msg], [msg, other]))
def test_read_answer_success(listener: Listener, buffer):
    listener.message_handler._received = buffer  # type: ignore
    assert listener.read_answer(cid) == msg_list


@pytest.mark.parametrize("buffer", ([msg], [msg, other]))
def test_read_answer_as_message_success(listener: Listener, buffer):
    listener.message_handler._received = buffer  # type: ignore
    assert listener.read_answer_as_message(cid) == msg


def test_ask_rpc(listener: Listener):
    response = Message("test", "receiver", conversation_id=cid,
                       data={'jsonrpc': "2.0", "result": None, "id": 1})
    listener.message_handler._received = [response]  # type: ignore
    listener.ask_rpc("receiver", method="test_method")
    sent_message = listener.message_handler._sent[0]  # type: ignore
    assert sent_message == Message(b"receiver", b"N.Pipe",
                                   conversation_id=sent_message.conversation_id,
                                   message_type=MessageTypes.JSON,
                                   data={'jsonrpc': "2.0", "method": "test_method", "id": 1})
