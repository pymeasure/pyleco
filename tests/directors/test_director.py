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

from pyleco.directors.director import Director
from pyleco.test import FakeCommunicator
from pyleco.core.message import Message, MessageTypes


cid = b"conversation_id;"


def fake_generate_conversation_id():
    return cid


@pytest.fixture
def director(monkeypatch):
    monkeypatch.setattr("pyleco.directors.director.generate_conversation_id",
                        fake_generate_conversation_id)
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id",
                        fake_generate_conversation_id)
    return Director(actor="actor", communicator=FakeCommunicator(name="director"))


def test_sign_out(director: Director):
    director.sign_out()
    assert director.communicator._signed_in is False  # type: ignore


def test_close(director: Director):
    director._own_communicator = True
    director.close()
    assert director.communicator._closed is True  # type: ignore


def test_context_manager():
    with Director(communicator=FakeCommunicator(name="director")) as director:
        communicator = director.communicator
        director._own_communicator = True
        communicator._closed = False  # type: ignore
    assert communicator._closed is True  # type: ignore


class Test_actor_check:
    def test_invalid_actor(self, director: Director):
        director.actor = None
        with pytest.raises(ValueError):
            director._actor_check(actor=None)

    def test_given_actor(self, director: Director):
        assert director._actor_check("another_actor") == "another_actor"

    def test_default_actor(self, director: Director):
        assert director._actor_check("") == "actor"


def test_ask_message(director: Director):
    rec = Message("director", "actor", conversation_id=cid)
    director.communicator._r = [rec]  # type: ignore
    result = director.ask_message()
    assert result == rec
    sent = director.communicator._s[0]  # type: ignore
    assert sent == Message(
        "actor",
        "director",
        conversation_id=cid,
    )


def test_get_rpc_capabilities(director: Director):
    data = {"name": "actor", "methods": []}
    director.communicator._r = [  # type: ignore
        Message("director", "actor", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "result": data, "jsonrpc": "2.0"
            })]
    result = director.get_rpc_capabilities()
    assert director.communicator._s == [  # type: ignore
        Message("actor", "director", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "method": "rpc.discover", "jsonrpc": "2.0"
            })]
    assert result == data


def test_shutdown_actor(director: Director):
    director.communicator._r = [  # type: ignore
        Message("director", "actor", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "result": None, "jsonrpc": "2.0"
            })]
    director.shut_down_actor()
    assert director.communicator._s == [  # type: ignore
        Message("actor", "director", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "method": "shut_down", "jsonrpc": "2.0"
            })]


def test_set_actor_log_level(director: Director):
    director.communicator._r = [  # type: ignore
        Message("director", "actor", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "result": None, "jsonrpc": "2.0"
            })]
    director.set_actor_log_level(30)
    assert director.communicator._s == [  # type: ignore
        Message("actor", "director", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "method": "set_log_level", "jsonrpc": "2.0", "params": {"level": "WARNING"}
            })]


def test_read_rpc_response(director: Director):
    director.communicator._r = [  # type: ignore
        Message("director", "actor", conversation_id=cid, message_type=MessageTypes.JSON, data={
            "id": 1, "result": 7.5, "jsonrpc": "2.0"
            })]
    assert director.read_rpc_response(conversation_id=cid) == 7.5


def test_read_binary_rpc_response(director: Director):
    director.communicator._r = [  # type: ignore
        Message(
            "director",
            "actor",
            conversation_id=cid,
            message_type=MessageTypes.JSON,
            data={"id": 1, "result": None, "jsonrpc": "2.0"},
            additional_payload=[b"123"],
        )
    ]
    assert director.read_rpc_response(conversation_id=cid, extract_additional_payload=True) == (
        None,
        [b"123"],
    )


def test_get_properties_async(director: Director):
    properties = ["a", "some"]
    cid = director.get_parameters_async(parameters=properties)
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "get_parameters", "params": {"parameters": properties},
              "jsonrpc": "2.0"}
    )]


def test_get_properties_async_string(director: Director):
    properties = ["some"]
    cid = director.get_parameters_async(parameters=properties[0])
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "get_parameters", "params": {"parameters": properties},
              "jsonrpc": "2.0"}
    )]


def test_set_properties_async(director: Director):
    properties = {"a": 5, "some": 7.3}
    cid = director.set_parameters_async(parameters=properties)
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "set_parameters", "params": {"parameters": properties},
              "jsonrpc": "2.0"}
    )]


def test_call_action_async_with_args_and_kwargs(director: Director):
    cid = director.call_action_async("action_name", "arg1", key1=1)
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "call_action", "params": {"action": "action_name",
                                                           "args": ["arg1"], "kwargs": {"key1": 1}},
              "jsonrpc": "2.0"}
        )]


def test_call_action_async_with_args_only(director: Director):
    cid = director.call_action_async("action_name", "arg1", 5)
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "call_action", "params": {"action": "action_name",
                                                           "args": ["arg1", 5]},
              "jsonrpc": "2.0"}
        )]


def test_call_action_async_with_kwargs_only(director: Director):
    cid = director.call_action_async("action_name", arg1=1, arg2="abc")
    assert director.communicator._s == [Message(  # type: ignore
        receiver="actor", sender="director", conversation_id=cid, message_type=MessageTypes.JSON,
        data={"id": 1, "method": "call_action", "params": {"action": "action_name",
                                                           "kwargs": {"arg1": 1, "arg2": "abc"}},
              "jsonrpc": "2.0"}
        )]


class Test_get_properties:
    properties = ["a", "some"]
    expected_result = {"a": 5, "some": 7}

    @pytest.fixture
    def director_gp(self, director: Director):
        director.communicator._r = [  # type: ignore
            Message("director", "actor", conversation_id=cid, message_type=MessageTypes.JSON, data={
                "id": 1, "result": self.expected_result, "jsonrpc": "2.0"
                })]
        self.result = director.get_parameters(parameters=self.properties)
        return director

    def test_message_sent(self, director_gp):
        assert director_gp.communicator._s == [Message(  # type: ignore
            "actor", "director", conversation_id=cid, message_type=MessageTypes.JSON, data={
                "id": 1, "method": "get_parameters", "params": {"parameters": self.properties},
                "jsonrpc": "2.0"})]

    def test_result(self, director_gp):
        assert self.result == self.expected_result
