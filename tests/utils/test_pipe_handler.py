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

from pyleco.core.message import Message
from pyleco.test import FakeContext

from pyleco.utils.pipe_handler import MessageBuffer, PipeHandler

cid = b"conversation_id;"  # conversation_id
header = b"".join((cid, b"mid", b"\x00"))
# the result
msg = Message(b"r", b"s", conversation_id=cid, message_id=b"mid")
msg_list = ("r", "s", cid, b"", None)
# some different message
other = Message(b"r", b"s", conversation_id=b"conversation_id9", message_id=b"mid")


@pytest.fixture
def message_buffer() -> MessageBuffer:
    message_buffer = MessageBuffer()
    message_buffer._buffer = [msg]
    return message_buffer


@pytest.fixture
def pipe_handler() -> PipeHandler:
    return PipeHandler(name="handler", context=FakeContext())  # type: ignore


def test_add_conversation_id(message_buffer: MessageBuffer):
    message_buffer.add_conversation_id(conversation_id=cid)
    assert cid in message_buffer._cids


class Test_add_response_message_successful:
    @pytest.fixture
    def message_buffer_added(self) -> MessageBuffer:
        # Arrange
        mb = MessageBuffer()
        assert mb._buffer == []
        mb.add_conversation_id(cid)
        # Act
        self.return_value = mb.add_response_message(msg)
        return mb

    def test_return_value(self, message_buffer_added):
        assert self.return_value is True

    def test_msg_in_buffer(self, message_buffer_added):
        assert message_buffer_added._buffer == [msg]

    def test_cid_cleared(self, message_buffer_added: MessageBuffer):
        assert message_buffer_added._cids == []


def test_add_fails_without_previous_cid():
    empty_message_buffer = MessageBuffer()
    assert empty_message_buffer.add_response_message(message=msg) is False
    assert empty_message_buffer._buffer == []


class Test_check_message_in_buffer:
    def test_message_is_in_first_place(self, message_buffer: MessageBuffer):
        assert message_buffer._check_message_in_buffer(conversation_id=cid) == msg
        assert message_buffer._buffer == []

    def test_no_suitable_message_in_buffer(self, message_buffer: MessageBuffer):
        assert message_buffer._check_message_in_buffer(conversation_id=b"other_cid") is None
        assert message_buffer._buffer != []

    def test_msg_somewhere_in_buffer(self, message_buffer: MessageBuffer):
        o2 = Message(b"r", b"s", conversation_id=b"conversation_id9", message_id=b"mi7")
        message_buffer._buffer = [other, msg, o2]
        assert message_buffer._check_message_in_buffer(conversation_id=cid) == msg
        assert message_buffer._buffer == [other, o2]


@pytest.mark.parametrize("buffer", (
        [msg],  # msg is only message
        [msg, other],  # msg is in the first place of the buffer
        [other, msg],  # msg is in the second and last place of the buffer
        [other, msg, other]  # msg is in the middle of the buffer
    ))
def test_retrieve_message_success(message_buffer: MessageBuffer, buffer):
    message_buffer._buffer = buffer
    original_length = len(buffer)
    assert message_buffer.retrieve_message(cid) == msg
    assert len(message_buffer._buffer) == original_length - 1


@pytest.mark.parametrize("buffer", (
        [],  # no message in buffer
        [other],  # other message in buffer
    ))
def test_retrieve_message_fail(message_buffer: MessageBuffer, buffer):
    message_buffer._buffer = buffer
    with pytest.raises(TimeoutError):
        message_buffer.retrieve_message(conversation_id=cid, tries=3, timeout=0.01)


def test_retrieve_message_after_waiting(message_buffer: MessageBuffer):
    # Arrange
    msg_list = [None, msg]

    def fake_check_message_in_buffer(conversation_id: bytes) -> Message | None:
        return msg_list.pop(0)
    message_buffer._check_message_in_buffer = fake_check_message_in_buffer  # type:ignore
    message_buffer._event.set()
    # Act + Assert
    assert message_buffer.retrieve_message(conversation_id=cid) == msg
    assert message_buffer._event.is_set() is False  # test that it did not return in the first read
    assert msg_list == []
