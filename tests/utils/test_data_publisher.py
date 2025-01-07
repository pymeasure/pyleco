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

import pickle
import pytest

from pyleco.utils.data_publisher import DataPublisher, DataMessage
from pyleco.test import FakeContext


@pytest.fixture
def publisher():
    publisher = DataPublisher(full_name="sender", context=FakeContext())  # type: ignore
    return publisher


def test_socket_type(publisher: DataPublisher):
    assert publisher.socket.socket_type == 1


def test_connection():
    publisher = DataPublisher(full_name="", host="localhost", port=12345,
                              context=FakeContext())  # type: ignore
    assert publisher.socket.addr == "tcp://localhost:12345"


def test_context_manager_closes_connection():
    with DataPublisher("", context=FakeContext()) as p:  # type: ignore
        pass
    assert p.socket.closed is True


def test_call_publisher_sends(publisher: DataPublisher):
    publisher(b"data")
    # assert
    message = DataMessage.from_frames(*publisher.socket._s.pop())  # type: ignore
    assert message.topic == publisher.full_name.encode()
    assert message.payload[0] == b"data"


def test_send_data(publisher: DataPublisher):
    publisher.send_data(
        data=b"data", topic=b"topic", conversation_id=b"cid", additional_payload=[b"1"]
    )
    assert publisher.socket._s == [[b"topic", b"cid\x00", b"data", b"1"]]


def test_send_message(publisher: DataPublisher):
    message = DataMessage.from_frames(b"topic", b"header", b"data")
    publisher.send_message(message=message)
    assert publisher.socket._s == [message.to_frames()]


def test_send_legacy(publisher: DataPublisher):
    value = 5.67
    publisher.send_legacy({'key': value})
    message = DataMessage.from_frames(*publisher.socket._s[0])  # type: ignore
    assert message.topic == b"key"
    assert message.payload[0] == pickle.dumps(value)
    assert message.message_type == 234


def test_set_full_name(publisher: DataPublisher):
    new_full_name = "new full name"
    publisher.set_full_name(new_full_name)
    assert publisher.full_name == new_full_name
