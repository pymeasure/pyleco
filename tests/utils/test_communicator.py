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

from unittest.mock import MagicMock

import pytest

from pyleco.core import VERSION_B
from pyleco.core.message import Message, MessageTypes
from pyleco.core.serialization import serialize_data
from pyleco.json_utils.errors import JSONRPCError, NOT_SIGNED_IN, NODE_UNKNOWN

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
    assert isinstance(c.socket, FakeSocket)


def test_context_manager_opens_connection():
    class FK2(FakeCommunicator):
        def __init__(self, **kwargs):
            super().__init__(auto_open=False, **kwargs)

        def sign_in(self):
            pass
    with FK2(name="Test") as c:
        assert isinstance(c.socket, FakeSocket)


class Test_close:
    @pytest.fixture
    def closed_communicator(self, communicator: Communicator, fake_cid_generation):
        message = Message("Test", "COORDINATOR", message_type=MessageTypes.JSON,
                          conversation_id=cid, data={
                              "jsonrcp": "2.0", "result": None, "id": 1,
                              })
        communicator.socket._r = [message.to_frames()]  # type: ignore
        communicator.close()
        return communicator

    def test_socket_closed(self, closed_communicator: Communicator):
        assert closed_communicator.socket.closed is True

    def test_signed_out(self, closed_communicator: Communicator):
        sign_out_message = Message.from_frames(*closed_communicator.socket._s.pop())  # type: ignore  # noqa
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


def test_reset(communicator: Communicator):
    communicator.close = MagicMock()  # type: ignore
    communicator.open = MagicMock()  # type: ignore
    # act
    communicator.reset()
    # assert
    communicator.close.assert_called_once()
    communicator.open.assert_called_once()


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_communicator_send(communicator: Communicator, kwargs, message, monkeypatch,
                           fake_cid_generation):
    monkeypatch.setattr("pyleco.utils.communicator.perf_counter", fake_time)
    communicator.send(**kwargs)
    assert communicator.socket._s.pop() == message  # type: ignore


def test_poll(communicator: Communicator):
    assert communicator.poll() == 0


class Test_ask_message:
    request = Message(receiver=b"N1.receiver", data="whatever", conversation_id=cid)
    response = Message(receiver=b"N1.Test", sender=b"N1.receiver", data=["xyz"],
                       message_type=MessageTypes.JSON,
                       conversation_id=cid)

    def test_ignore_ping(self, communicator: Communicator):
        ping_message = Message(receiver=b"N1.Test", sender=b"N1.COORDINATOR",
                               message_type=MessageTypes.JSON,
                               data={"id": 0, "method": "pong", "jsonrpc": "2.0"})
        communicator.socket._r = [  # type: ignore
            ping_message.to_frames(),
            self.response.to_frames()]
        communicator.ask_message(self.request)
        assert communicator.socket._s == [self.request.to_frames()]

    def test_sign_in(self, communicator: Communicator, fake_cid_generation):
        communicator.sign_in = MagicMock()  # type: ignore
        not_signed_in = Message(receiver="N1.Test", sender="N1.COORDINATOR",
                                message_type=MessageTypes.JSON,
                                conversation_id=cid,
                                data={"id": None,
                                      "error": NOT_SIGNED_IN.model_dump(),
                                      "jsonrpc": "2.0"},
                                )
        communicator.socket._r = [  # type: ignore
            not_signed_in.to_frames(),
            self.response.to_frames()]
        response = communicator.ask_message(self.request)
        # assert that the message is sent once
        assert communicator.socket._s.pop(0) == self.request.to_frames()  # type: ignore
        # assert that it tries to sign in
        communicator.sign_in.assert_called()
        # assert that the message is called a second time
        assert communicator.socket._s == [self.request.to_frames()]
        # assert that the correct response is returned
        assert response == self.response

    def test_ignore_wrong_response(self, communicator: Communicator,
                                   caplog: pytest.LogCaptureFixture):
        """A wrong response should not be returned."""
        caplog.set_level(10)
        m = Message(receiver="whatever", sender="s", message_type=MessageTypes.JSON,
                    data={'jsonrpc': "2.0"}).to_frames()
        communicator.socket._r = [m, self.response.to_frames()]  # type: ignore
        assert communicator.ask_message(self.request) == self.response

    def test_sign_in_fails_several_times(self, communicator: Communicator, fake_cid_generation):
        not_signed_in = Message(receiver="communicator", sender="N1.COORDINATOR",
                                message_type=MessageTypes.JSON,
                                data={"id": None,
                                      "error": NOT_SIGNED_IN.model_dump(),
                                      "jsonrpc": "2.0"},
                                ).to_frames()
        communicator.sign_in = MagicMock()  # type: ignore
        communicator.socket._r = [not_signed_in, not_signed_in]  # type: ignore
        with pytest.raises(ConnectionRefusedError):
            communicator.ask_message(self.request)

    @pytest.mark.xfail(True, reason="Unsure whether it should work that way.")
    def test_ask_message_with_error(self, communicator: Communicator):
        response = Message(receiver="communicator", sender="N1.COORDINATOR",
                        message_type=MessageTypes.JSON, conversation_id=cid,
                        data={"id": None,
                                "error": NODE_UNKNOWN.model_dump(),
                                "jsonrpc": "2.0"},
                        )
        communicator.socket._r = [response.to_frames()]  # type: ignore
        with pytest.raises(JSONRPCError, match=NODE_UNKNOWN.message):
            communicator.ask_message(Message("receiver", conversation_id=cid))


def test_ask_rpc(communicator: Communicator, fake_cid_generation):
    received = Message(receiver=b"N1.Test", sender=b"N1.receiver",
                       conversation_id=cid)
    received.payload = [b"""{"jsonrpc": "2.0", "result": 123.45, "id": "1"}"""]
    communicator.socket._r = [received.to_frames()]  # type: ignore
    response = communicator.ask_rpc(receiver="N1.receiver", method="test_method", some_arg=4)
    assert communicator.socket._s == [
        Message(b'N1.receiver', b'Test',
                conversation_id=cid,
                message_type=MessageTypes.JSON,
                data={"id": 1, "method": "test_method",
                      "params": {"some_arg": 4}, "jsonrpc": "2.0"}).to_frames()]
    assert response == 123.45


def test_communicator_sign_in(fake_cid_generation, communicator: Communicator):
    communicator.socket._r = [  # type: ignore
        Message(b"N2.n", b"N2.COORDINATOR",
                conversation_id=cid, message_type=MessageTypes.JSON,
                data={"id": 1, "result": None, "jsonrpc": "2.0"}).to_frames()]
    communicator.sign_in()
    assert communicator.namespace == "N2"


def test_get_capabilities(communicator: Communicator, fake_cid_generation):
    communicator.socket._r = [  # type: ignore
        Message("communicator", "sender", conversation_id=cid,
                message_type=MessageTypes.JSON,
                data={"id": 1, "result": 6, "jsonrpc": "2.0"}
                ).to_frames()
    ]
    result = communicator.get_capabilities(receiver="rec")
    sent = Message.from_frames(*communicator.socket._s.pop())  # type: ignore
    assert sent.data == {"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}
    assert result == 6


def test_ask_json(communicator: Communicator, fake_cid_generation):
    response = Message("communicator", sender="rec", conversation_id=cid,
                       data="super response")
    communicator.socket._r = [response.to_frames()]  # type: ignore
    json_string = "[5, 6.7]"
    # act
    result = communicator.ask_json(receiver="rec", json_string=json_string)
    # assert
    sent = Message.from_frames(*communicator.socket._s.pop())  # type: ignore
    assert sent.data == [5, 6.7]
    assert result == b"super response"
