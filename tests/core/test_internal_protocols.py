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

from pyleco.core.message import Message, MessageTypes
from pyleco.core.internal_protocols import CommunicatorProtocol
from pyleco.test import FakeCommunicator
from pyleco.json_utils.errors import JSONRPCError

cid = b"conversation_id;"

# Test the utility methods of the CommunicatorProtocol


@pytest.fixture
def communicator() -> CommunicatorProtocol:
    return FakeCommunicator(name="communicator")


def test_full_name_without_namespace(communicator: FakeCommunicator):
    communicator.namespace = None
    assert communicator.full_name == "communicator"


def test_full_name_with_namespace(communicator: FakeCommunicator):
    communicator.namespace = "N1"
    assert communicator.full_name == "N1.communicator"


def test_send(communicator: FakeCommunicator):
    kwargs = dict(receiver="rec", message_type=MessageTypes.JSON, data=[4, 5], conversation_id=cid)
    communicator.send(**kwargs)  # type: ignore
    assert communicator._s[0] == Message(sender="communicator", **kwargs)  # type: ignore


class Test_ask:
    response = Message(receiver="communicator", sender="rec", conversation_id=cid)

    @pytest.fixture
    def communicator_asked(self, communicator: FakeCommunicator):
        communicator._r = [self.response]
        return communicator

    def test_sent(self, communicator_asked: FakeCommunicator):
        communicator_asked.ask(receiver="rec", conversation_id=cid)
        assert communicator_asked._s == [Message(receiver="rec", sender="communicator",
                                                 conversation_id=cid)]

    def test_read(self, communicator_asked: FakeCommunicator):
        response = communicator_asked.ask(receiver="rec", conversation_id=cid)
        assert response == self.response


class Test_interpret_rpc_response:
    def test_valid_message(self, communicator: FakeCommunicator):
        message = Message(receiver="rec", data={"jsonrpc": "2.0", "result": 6.0, "id": 7})
        assert communicator.interpret_rpc_response(message) == 6.0

    def test_error(self, communicator: FakeCommunicator):
        message = Message(receiver="rec", data={"jsonrpc": "2.0",
                                                "error": {"code": -1, "message": "abc"}, "id": 7})
        with pytest.raises(JSONRPCError):
            communicator.interpret_rpc_response(message)

    def test_json_binary_response(self, communicator: FakeCommunicator):
        message = Message(
            receiver="rec",
            data={"jsonrpc": "2.0", "result": None, "id": 7},
            additional_payload=[b"abcd", b"efgh"],
        )
        assert communicator.interpret_rpc_response(message, extract_additional_payload=True) == (
            None,
            [
                b"abcd",
                b"efgh",
            ],
        )

    def test_ignore_additional_payload_if_not_desired(self, communicator: FakeCommunicator):
        message = Message(
            receiver="rec",
            data={"jsonrpc": "2.0", "result": None, "id": 7},
            additional_payload=[b"abcd"],
        )
        assert (
            communicator.interpret_rpc_response(message, extract_additional_payload=False) is None
        )

    def test_without_additional_payload_return_empty_list(self, communicator: FakeCommunicator):
        message = Message(
            receiver="rec",
            data={"jsonrpc": "2.0", "result": None, "id": 7},
        )
        assert communicator.interpret_rpc_response(message, extract_additional_payload=True) == (
            None,
            [],
        )

    def test_json_value_and_binary_payload(self, communicator: FakeCommunicator):
        message = Message(
            receiver="rec",
            data={"jsonrpc": "2.0", "result": 6, "id": 7},
            additional_payload=[b"abcd"],
        )
        assert communicator.interpret_rpc_response(message, extract_additional_payload=True) == (
            6,
            [b"abcd"],
        )


class Test_ask_rpc:
    response = Message(receiver="communicator", sender="rec", conversation_id=cid,
                       message_type=MessageTypes.JSON,
                       data={
                           "jsonrpc": "2.0",
                           "result": 5,
                           "id": 1,
                           })

    @pytest.fixture
    def communicator_asked(self, communicator: FakeCommunicator):
        communicator._r = [self.response]
        return communicator

    def test_sent(self, communicator_asked: FakeCommunicator):
        communicator_asked.ask_rpc(receiver="rec", method="test_method", par1=5)
        sent = communicator_asked._s[0]
        assert communicator_asked._s == [Message(receiver="rec", sender="communicator",
                                                 conversation_id=sent.conversation_id,
                                                 message_type=MessageTypes.JSON,
                                                 data={
                                                     "jsonrpc": "2.0",
                                                     "method": "test_method",
                                                     "id": 1,
                                                     "params": {'par1': 5},
                                                 })]

    def test_sent_with_additional_payload(self, communicator_asked: FakeCommunicator):
        communicator_asked.ask_rpc(
            receiver="rec", method="test_method", par1=5, additional_payload=[b"12345"]
        )
        sent = communicator_asked._s[0]
        assert communicator_asked._s == [
            Message(
                receiver="rec",
                sender="communicator",
                conversation_id=sent.conversation_id,
                message_type=MessageTypes.JSON,
                data={
                    "jsonrpc": "2.0",
                    "method": "test_method",
                    "id": 1,
                    "params": {"par1": 5},
                },
                additional_payload=[b"12345"],
            )
        ]

    def test_read(self, communicator_asked: FakeCommunicator):
        result = communicator_asked.ask_rpc(receiver="rec", method="test_method", par1=5)
        assert result == 5
