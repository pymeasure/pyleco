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

from unittest.mock import MagicMock

import pytest

from pyleco.core.data_message import DataMessage
from pyleco.test import FakeContext, FakeSocket
from pyleco.utils.events import SimpleEvent
from pyleco.utils.extended_message_handler import ExtendedMessageHandler


@pytest.fixture
def handler():
    handler = ExtendedMessageHandler(name="handler",
                                     context=FakeContext())  # type: ignore
    handler.namespace = "N1"
    handler.stop_event = SimpleEvent()
    handler.subscriber = FakeSocket(2)  # type: ignore
    handler.handle_subscription_message = MagicMock()  # it is not defined
    handler.handle_subscription_message.assert_called_once_with
    return handler


def test_read_subscription_message_calls_handle(handler: ExtendedMessageHandler):
    message = DataMessage("", data="[]")
    handler.subscriber._r = [message.to_frames()]  # type: ignore
    handler.read_subscription_message()
    # assert
    handler.handle_subscription_message.assert_called_once_with(message)  # type: ignore


def test_subscribe_single(handler: ExtendedMessageHandler):
    handler.subscribe_single(b"topic")
    assert handler.subscriber._subscriptions == [b"topic"]  # type: ignore
    assert handler._subscriptions == [b"topic"]


@pytest.mark.parametrize("topics, result", (
        ("topic", [b"topic"]),  # single string
        (["topic1", "topic2"], [b"topic1", b"topic2"]),  # list of strings
        (("topic1", "topic2"), [b"topic1", b"topic2"]),  # tuple of strings
))
def test_subscribe(handler: ExtendedMessageHandler, topics, result):
    handler.subscribe(topics)
    assert handler._subscriptions == result


def test_unsubscribe_single(handler: ExtendedMessageHandler):
    handler._subscriptions = [b"topic"]
    handler.subscriber._subscriptions = [b"topic"]  # type: ignore
    handler.unsubscribe_single(b"topic")
    assert handler._subscriptions == []
    assert handler.subscriber._subscriptions == []  # type: ignore


@pytest.mark.parametrize("topics, result", (
        ("topic", [b"topic"]),  # single string
        (["topic1", "topic2"], [b"topic1", b"topic2"]),  # list of strings
        (("topic1", "topic2"), [b"topic1", b"topic2"]),  # tuple of strings
))
def test_unsubscribe(handler: ExtendedMessageHandler, topics, result):
    handler._subscriptions = result
    handler.unsubscribe(topics)
    assert handler._subscriptions == []


def test_unsubscribe_all(handler: ExtendedMessageHandler):
    handler._subscriptions = [b"topic1", b"topic2"]
    handler.unsubscribe_all()
    assert handler._subscriptions == []
