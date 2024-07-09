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

import json
import pickle
from unittest.mock import MagicMock

import pytest

from pyleco.core.data_message import DataMessage
from pyleco.core.message import Message, MessageTypes
from pyleco.test import FakeContext, FakeSocket, handle_request_message, assert_response_is_result
from pyleco.utils.events import SimpleEvent
from pyleco.utils.extended_message_handler import ExtendedMessageHandler


CID = b"conversation_id;"


@pytest.fixture
def handler():
    handler = ExtendedMessageHandler(name="handler",
                                     context=FakeContext())  # type: ignore
    handler.namespace = "N1"
    handler.stop_event = SimpleEvent()
    handler.subscriber = FakeSocket(2)  # type: ignore
    handler.handle_subscription_message = MagicMock()  # it is not defined
    return handler


@pytest.fixture()
def fake_cid_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generate_cid() -> bytes:
        return CID
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


def test_read_subscription_message_calls_handle(handler: ExtendedMessageHandler):
    message = DataMessage("", data="[]")
    handler.subscriber._r = [message.to_frames()]  # type: ignore
    handler.read_subscription_message()
    # assert
    handler.handle_subscription_message.assert_called_once_with(message)  # type: ignore


def test_handle_subscription_message_raises_not_implemented():
    handler = ExtendedMessageHandler(name="handler", context=FakeContext())  # type: ignore
    with pytest.raises(NotImplementedError):
        handler.handle_subscription_message(DataMessage(b"topic"))


def test_read_subscription_message_calls_handle_legacy(handler: ExtendedMessageHandler):
    message = DataMessage("", data="[]", message_type=234)
    handler.handle_full_legacy_subscription_message = MagicMock()  # type: ignore[method-assign]
    handler.subscriber._r = [message.to_frames()]  # type: ignore
    handler.read_subscription_message()
    # assert
    handler.handle_full_legacy_subscription_message.assert_called_once_with(message)  # type: ignore


def test_subscribe_single(handler: ExtendedMessageHandler):
    handler.subscribe_single(b"topic")
    assert handler.subscriber._subscriptions == [b"topic"]  # type: ignore
    assert handler._subscriptions == [b"topic"]


def test_subscribe_single_again(handler: ExtendedMessageHandler, caplog: pytest.LogCaptureFixture):
    # arrange
    handler.subscribe_single(b"topic")
    caplog.set_level(10)
    # act
    handler.subscribe_single(b"topic")
    assert caplog.messages[-1] == f"Already subscribed to {b'topic'!r}."


@pytest.mark.parametrize("topics, result", (
        ("topic", [b"topic"]),  # single string
        (["topic1", "topic2"], [b"topic1", b"topic2"]),  # list of strings
        (("topic1", "topic2"), [b"topic1", b"topic2"]),  # tuple of strings
))
def test_subscribe(handler: ExtendedMessageHandler, topics, result):
    handle_request_message(handler, "subscribe", topics)
    assert_response_is_result(handler)
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
    # act
    handle_request_message(handler, "unsubscribe", topics)
    assert_response_is_result(handler)
    assert handler._subscriptions == []


def test_unsubscribe_all(handler: ExtendedMessageHandler):
    handler._subscriptions = [b"topic1", b"topic2"]
    # act
    handle_request_message(handler, "unsubscribe_all")
    # assert
    assert_response_is_result(handler)
    assert handler._subscriptions == []


class Test_handle_full_legacy_subscription_message:
    @pytest.fixture
    def handler_hfl(self, handler: ExtendedMessageHandler) -> ExtendedMessageHandler:
        handler.handle_subscription_data = MagicMock()  # type: ignore[method-assign]
        return handler

    def test_handle_pickled_message(self, handler_hfl: ExtendedMessageHandler):
        data = ["some", "data", 5]
        handler_hfl.handle_full_legacy_subscription_message(
            DataMessage("topic", data=pickle.dumps(data), message_type=234)
        )
        handler_hfl.handle_subscription_data.assert_called_once_with({"topic": data})  # type: ignore

    def test_handle_json_message(self, handler_hfl: ExtendedMessageHandler):
        data = ["some", "data", 5]
        handler_hfl.handle_full_legacy_subscription_message(
            DataMessage("topic", data=json.dumps(data), message_type=235)
        )
        handler_hfl.handle_subscription_data.assert_called_once_with({"topic": data})  # type: ignore

    def test_handle_unknown_message_type(self, handler_hfl: ExtendedMessageHandler):
        with pytest.raises(ValueError):
            handler_hfl.handle_full_legacy_subscription_message(
                DataMessage("topic", data="", message_type=210)
            )

    def test_handle_subscription_data(self, handler: ExtendedMessageHandler):
        with pytest.raises(NotImplementedError):
            handler.handle_subscription_data({})


def test_subscribe_via_command(handler: ExtendedMessageHandler, fake_cid_generation):
    handler.socket._r = [  # type: ignore
        Message(
            "handler",
            "topic",
            {"jsonrpc": "2.0", "id": 1, "result": None},
            message_type=MessageTypes.JSON,
            conversation_id=CID,
        ).to_frames()
    ]
    handler.subscribe_via_control("topic")
    assert Message.from_frames(*handler.socket._s[0]) ==  Message(  # type: ignore
            "topic",
            "N1.handler",
            {"jsonrpc": "2.0", "id": 1, "method": "register_subscriber"},
            message_type=MessageTypes.JSON,
            conversation_id=CID,
        )


def test_unsubscribe_via_command(handler: ExtendedMessageHandler, fake_cid_generation):
    handler.socket._r = [  # type: ignore
        Message(
            "handler",
            "topic",
            {"jsonrpc": "2.0", "id": 1, "result": None},
            message_type=MessageTypes.JSON,
            conversation_id=CID,
        ).to_frames()
    ]
    handler.unsubscribe_via_control("topic")
    assert Message.from_frames(*handler.socket._s[0]) ==  Message(  # type: ignore
            "topic",
            "N1.handler",
            {"jsonrpc": "2.0", "id": 1, "method": "unregister_subscriber"},
            message_type=MessageTypes.JSON,
            conversation_id=CID,
        )


@pytest.fixture
def data_message() -> DataMessage:
    return DataMessage(
            topic="topic", conversation_id=CID, data=b"0", additional_payload=[b"1", b"2"]
        )


def test_set_subscription_message(handler: ExtendedMessageHandler, data_message: DataMessage):
    handler.current_message = Message(
        "abc",
        sender="topic",
        data={"id": 1, "method": "set_subscription_message", "jsonrpc": "2.0"},
        conversation_id=CID,
        message_type=MessageTypes.JSON,
        additional_payload=data_message.payload,
    )
    def store_data(data_message):
        global _data
        _data = data_message

    handler.handle_subscription_message = store_data  # type: ignore
    # act
    handler.set_subscription_message()
    assert _data == data_message
