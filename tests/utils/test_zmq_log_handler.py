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

import pytest

from pyleco.test import FakeContext
from pyleco.utils.zmq_log_handler import ZmqLogHandler, DataMessage


@pytest.fixture
def handler() -> ZmqLogHandler:
    return ZmqLogHandler(context=FakeContext(), full_name="fullname", port=12345)  # type: ignore


def test_init_(handler: ZmqLogHandler):
    assert handler.full_name == "fullname"


def test_init_address(handler: ZmqLogHandler):
    assert handler.queue.socket.addr == "tcp://localhost:12345"  # type: ignore


def test_enqueue(handler: ZmqLogHandler):
    handler.enqueue("whatever")
    message = DataMessage.from_frames(*handler.queue.socket._s.pop())  # type: ignore
    assert message.topic == b"fullname"
    assert message.payload == [b'whatever']
