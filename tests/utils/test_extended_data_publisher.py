#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
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

from pyleco.test import FakeContext
from pyleco.core.message import Message, MessageTypes
from pyleco.core.data_message import DataMessage
from pyleco.json_utils.json_objects import Notification
from pyleco.utils.extended_data_publisher import ExtendedDataPublisher


CID = b"conversation_id;"
messages = []  # for tests

@pytest.fixture
def fake_send_message():
    global messages
    messages = []
    def _fsm(message: Message):
        global messages
        messages.append(message)
    return _fsm


@pytest.fixture
def publisher(fake_send_message) -> ExtendedDataPublisher:
    publisher = ExtendedDataPublisher(
        "fn", send_message_method=fake_send_message,
        context=FakeContext(),  # type: ignore
    )
    return publisher


@pytest.fixture
def data_message() -> DataMessage:
    return DataMessage(
            topic="topic", conversation_id=CID, data=b"0", additional_payload=[b"1", b"2"]
        )


def test_register_subscribers(publisher: ExtendedDataPublisher):
    # act
    publisher.register_subscriber("abcdef")
    assert b"abcdef" in publisher.subscribers

    publisher.register_subscriber(b"ghi")
    assert b"ghi" in publisher.subscribers


def test_unregister_subscribers(publisher: ExtendedDataPublisher):
    # arrange
    publisher.subscribers.add(b"abc")
    publisher.subscribers.add(b"def")
    # act
    # str
    publisher.unregister_subscriber("abc")
    assert b"abc" not in publisher.subscribers
    # bytes
    publisher.unregister_subscriber(b"def")
    assert b"def" not in publisher.subscribers
    # assert that no error is raised at repeated unregistering
    publisher.unregister_subscriber(b"def")


@pytest.mark.parametrize("receivers", (set(), {b"abc"}, {b"abc", b"def"}, {"string"}))
def test_convert(publisher: ExtendedDataPublisher, receivers, data_message: DataMessage):
    msgs = publisher.convert_data_message_to_messages(data_message, receivers=receivers)
    for rec, msg in zip(receivers, msgs, strict=True):
        assert msg == Message(
            receiver=rec,
            data=Notification(method="add_subscription_message"),
            conversation_id=CID,
            message_type=MessageTypes.JSON,
            additional_payload=data_message.payload,
        )


def test_send_message(publisher: ExtendedDataPublisher, data_message: DataMessage):
    # arrange
    publisher.register_subscriber("abc")
    # act
    publisher.send_message(data_message)
    # assert that the data message is sent
    assert publisher.socket._s == [data_message.to_frames()]
    # assert that the control message is sent
    global messages
    assert messages == [
        Message(
            "abc",
            data=Notification(method="add_subscription_message"),
            conversation_id=CID,
            message_type=MessageTypes.JSON,
            additional_payload=data_message.payload,
        )
    ]
