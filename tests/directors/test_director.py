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

from pyleco.directors.director import Director
from pyleco.test import FakeCommunicator
from pyleco.core.message import Message


cid = b"conversation_id;"


def fake_generate_conversation_id():
    return cid


@pytest.fixture
def director(monkeypatch):
    monkeypatch.setattr("pyleco.directors.director.generate_conversation_id",
                        fake_generate_conversation_id)
    return Director(actor="actor", communicator=FakeCommunicator(name="director"))


def test_ask(director: Director):
    director.communicator._r = [Message("director", "actor", conversation_id=cid, data={
        "id": 1, "result": 123.456, "jsonrpc": "2.0"
    })]
    response = director.ask(actor=None)
    assert director.communicator._s == [Message("actor", "director", conversation_id=cid)]
    assert response == 123.456


def test_shutdown_actor(director: Director):
    director.communicator._r = [Message("director", "actor", conversation_id=cid, data={
        "id": 1, "result": None, "jsonrpc": "2.0"
    })]
    director.shut_down_actor()
    assert director.communicator._s == [Message("actor", "director", conversation_id=cid, data={
        "id": 1, "method": "shut_down", "jsonrpc": "2.0"
    })]


def test_get_properties_async(director: Director):
    properties = ["a", "some"]
    cid = director.get_parameters_async(parameters=properties)
    assert director.communicator._s == [Message(
        receiver="actor", sender="director", conversation_id=cid,
        data={"id": 1, "method": "get_parameters", "params": {"parameters": properties},
              "jsonrpc": "2.0"}
    )]


def test_set_properties_async(director: Director):
    properties = {"a": 5, "some": 7.3}
    cid = director.set_parameters_async(parameters=properties)
    assert director.communicator._s == [Message(
        receiver="actor", sender="director", conversation_id=cid,
        data={"id": 1, "method": "set_parameters", "params": {"parameters": properties},
              "jsonrpc": "2.0"}
    )]


class Test_get_properties:
    properties = ["a", "some"]
    expected_result = {"a": 5, "some": 7}

    @pytest.fixture
    def director_gp(self, director: Director):
        director.communicator._r = [Message("director", "actor", conversation_id=cid, data={
            "id": 1, "result": self.expected_result, "jsonrpc": "2.0"
        })]
        self.result = director.get_parameters(parameters=self.properties)
        return director

    def test_message_sent(self, director_gp):
        assert director_gp.communicator._s == [Message(
            "actor", "director", conversation_id=cid, data={
                "id": 1, "method": "get_parameters", "params": {"parameters": self.properties},
                "jsonrpc": "2.0"})]

    def test_result(self, director_gp):
        assert self.result == self.expected_result