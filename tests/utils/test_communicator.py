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

from pyleco.core import VERSION_B
from pyleco.core.message import Message, MessageTypes
from pyleco.errors import NOT_SIGNED_IN
from pyleco.core.serialization import serialize_data

from pyleco.utils.communicator import Communicator
from pyleco.test import FakeSocket, FakeContext


cid = b"conversation_id;"
header = b"".join((cid, b"\x00" * 3, b"\x01"))


message_tests = (
    ({'receiver': "broker", 'data': [["GET", [1, 2]], ["GET", 3]], 'sender': 's',
      'message_type': MessageTypes.JSON},
     [VERSION_B, b"broker", b"s", header, serialize_data([["GET", [1, 2]], ["GET", 3]])]),
    ({'receiver': "someone", 'conversation_id': cid, 'sender': "ego", 'message_id': b"mid"},
     [VERSION_B, b'someone', b'ego', b'conversation_id;mid\x00']),
    ({'receiver': "router", 'sender': "origin"},
     [VERSION_B, b"router", b"origin", header[:-1] + b"\x00"]),
)


def fake_time():
    return 0


def fake_randbytes(n):
    return b"\01" * n


def fake_generate_cid():
    return cid


@pytest.fixture()
def fake_cid_generation(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


# intercom
class FakeCommunicator(Communicator):
    def open(self, context=None):
        super().open(context=FakeContext())  # type: ignore


@pytest.fixture()
def communicator() -> Communicator:
    communicator = FakeCommunicator(name="Test")
    communicator._last_beat = float("inf")
    return communicator


def test_name():
    c = FakeCommunicator(name="Test")
    assert c.name == "Test"


def test_auto_open():
    c = FakeCommunicator(name="Test", auto_open=True)
    assert isinstance(c.connection, FakeSocket)


def test_context_manager_opens_connection():
    class FK2(FakeCommunicator):
        def __init__(self, **kwargs):
            super().__init__(auto_open=False, **kwargs)

        def sign_in(self):
            pass
    with FK2(name="Test") as c:
        assert isinstance(c.connection, FakeSocket)


class Test_close:
    @pytest.fixture
    def closed_communicator(self, communicator: Communicator, fake_cid_generation):
        message = Message("Test", "COORDINATOR", message_type=MessageTypes.JSON,
                          conversation_id=cid, data={
                              "jsonrcp": "2.0", "result": None, "id": 1,
                              })
        communicator.connection._r = [message.to_frames()]  # type: ignore
        communicator.close()
        return communicator

    def test_socket_closed(self, closed_communicator: Communicator):
        assert closed_communicator.connection.closed is True

    def test_signed_out(self, closed_communicator: Communicator):
        sign_out_message = Message.from_frames(*closed_communicator.connection._s.pop())  # type: ignore  # noqa
        assert sign_out_message == Message(
            "COORDINATOR",
            "Test",
            conversation_id=sign_out_message.conversation_id,
            message_type=MessageTypes.JSON,
            data={'jsonrpc': "2.0", 'method': "sign_out", "id": 1}
        )

    def test_no_error_without_socket(self):
        communicator = FakeCommunicator("Test", auto_open=False)
        communicator.close()
        # no error raised


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_communicator_send(communicator: Communicator, kwargs, message, monkeypatch,
                           fake_cid_generation):
    monkeypatch.setattr("pyleco.utils.communicator.perf_counter", fake_time)
    communicator.send(**kwargs)
    assert communicator.connection._s.pop() == message  # type: ignore


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_communicator_read(communicator: Communicator, kwargs, message):
    communicator.connection._r.append(message)  # type: ignore
    response = communicator.read()
    assert response.receiver == kwargs.get('receiver').encode()
    assert response.conversation_id == kwargs.get('conversation_id', cid)
    assert response.sender == kwargs.get('sender', "").encode()
    assert response.header_elements.message_id == kwargs.get('message_id', b"\x00\x00\x00")
    assert response.data == kwargs.get("data")


class Test_ask_raw:
    request = Message(receiver=b"N1.receiver", data="whatever")
    response = Message(receiver=b"N1.Test", sender=b"N1.receiver", data=["xyz"],
                       message_type=MessageTypes.JSON,
                       conversation_id=request.conversation_id)

    def test_ignore_ping(self, communicator: Communicator):
        ping_message = Message(receiver=b"N1.Test", sender=b"N1.COORDINATOR",
                               message_type=MessageTypes.JSON,
                               data={"id": 0, "method": "pong", "jsonrpc": "2.0"})
        communicator.connection._r = [  # type: ignore
            ping_message.to_frames(),
            self.response.to_frames()]
        communicator.ask_raw(self.request)
        assert communicator.connection._s == [self.request.to_frames()]

    def test_sign_in(self, communicator: Communicator):
        communicator.sign_in = MagicMock()  # type: ignore
        not_signed_in = Message(receiver="N1.Test", sender="N1.COORDINATOR",
                                message_type=MessageTypes.JSON,
                                data={"id": None,
                                      "error": NOT_SIGNED_IN.model_dump(),
                                      "jsonrpc": "2.0"},
                                )
        communicator.connection._r = [  # type: ignore
            not_signed_in.to_frames(),
            self.response.to_frames()]
        response = communicator.ask_raw(self.request)
        print("result", response)
        assert communicator.connection._s.pop(0) == self.request.to_frames()  # type: ignore
        communicator.sign_in.assert_called()
        assert communicator.connection._s == [self.request.to_frames()]

    def test_ignore_wrong_response(self, communicator: Communicator,
                                   caplog: pytest.LogCaptureFixture):
        """A wrong response should not be returned."""
        caplog.set_level(10)
        m = Message(receiver="whatever", sender="s", message_type=MessageTypes.JSON,
                    data={'jsonrpc': "2.0"}).to_frames()
        communicator.connection._r = [m, self.response.to_frames()]  # type: ignore
        assert communicator.ask_raw(self.request) == self.response
        assert caplog.records[-1].msg.startswith("Message with different conversation id received:")


def test_ask_rpc(communicator: Communicator, fake_cid_generation):
    received = Message(receiver=b"N1.Test", sender=b"N1.receiver",
                       conversation_id=cid)
    received.payload = [b"""{"jsonrpc": "2.0", "result": 123.45, "id": "1"}"""]
    communicator.connection._r = [received.to_frames()]  # type: ignore
    response = communicator.ask_rpc(receiver="N1.receiver", method="test_method", some_arg=4)
    assert communicator.connection._s == [
        Message(b'N1.receiver', b'Test',
                conversation_id=cid,
                message_type=MessageTypes.JSON,
                data={"id": 1, "method": "test_method",
                      "params": {"some_arg": 4}, "jsonrpc": "2.0"}).to_frames()]
    assert response == 123.45


def test_communicator_sign_in(fake_cid_generation, communicator: Communicator):
    communicator.connection._r = [  # type: ignore
        Message(b"N2.n", b"N2.COORDINATOR",
                conversation_id=cid, message_type=MessageTypes.JSON,
                data={"id": 1, "result": None, "jsonrpc": "2.0"}).to_frames()]
    communicator.sign_in()
    assert communicator.namespace == "N2"
