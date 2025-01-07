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

from __future__ import annotations
import logging
import time
from typing import Optional
from unittest.mock import MagicMock

import pytest

from pyleco.test import FakeSocket
from pyleco.core.message import Message, MessageTypes
from pyleco.json_utils.rpc_generator import RPCGenerator
from pyleco.json_utils.errors import DUPLICATE_NAME
from pyleco.json_utils.json_objects import ErrorResponse

from pyleco.utils.base_communicator import BaseCommunicator, MessageBuffer


cid = b"conversation_id;"
header = b"".join((cid, b"\x00" * 4))


def fake_generate_cid():
    return cid


@pytest.fixture()
def fake_cid_generation(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


class FakeBaseCommunicator(BaseCommunicator):

    def __init__(self, name="communicator") -> None:
        self.name = name
        self.setup_message_buffer()
        self.socket = FakeSocket(0)  # type: ignore
        self.log = logging.getLogger()
        self.rpc_generator = RPCGenerator()

        # For tests
        self._s: list[Message] = []
        self._r: list[Message] = []

    def _send_socket_message(self, message: Message) -> None:
        self._s.append(message)

    def _read_socket_message(self, timeout: Optional[float] = None) -> Message:
        if self._r:
            return self._r.pop(0)
        raise TimeoutError


@pytest.fixture
def buffer() -> MessageBuffer:
    return MessageBuffer()


@pytest.fixture
def communicator() -> FakeBaseCommunicator:
    return FakeBaseCommunicator()


m1 = Message(receiver="N1.communicator", sender="xy")  # some message
mr = Message(receiver="N1.communicator", sender="xy", conversation_id=cid)  # requested message
m2 = Message(receiver="N1.communicator", sender="xy")  # another message


def test_cid_in_buffer(buffer: MessageBuffer):
    assert buffer.is_conversation_id_requested(cid) is False
    buffer.add_conversation_id(cid)
    assert buffer.is_conversation_id_requested(cid) is True
    buffer.remove_conversation_id(cid)
    assert buffer.is_conversation_id_requested(cid) is False


def test_remove_cid_without_cid_raises_no_exception(buffer: MessageBuffer):
    buffer.remove_conversation_id(cid)
    # assert that no error is raised


def test_retrieve_requested_message(buffer: MessageBuffer):
    buffer.add_conversation_id(cid)
    buffer.add_message(m1)
    buffer.add_message(mr)
    buffer.add_message(m2)
    ret = buffer.retrieve_message(cid)
    assert ret == mr
    assert buffer.is_conversation_id_requested(cid) is False


def test_retrieve_free_message(buffer: MessageBuffer):
    buffer.add_conversation_id(cid)
    buffer.add_message(mr)
    buffer.add_message(m2)
    ret = buffer.retrieve_message()
    assert ret == m2


def test_free_message_not_found(buffer: MessageBuffer):
    buffer.add_message(mr)
    buffer.add_conversation_id(cid)
    assert buffer.retrieve_message(None) is None


def test_requested_message_not_found(buffer: MessageBuffer):
    buffer.add_message(m1)
    assert buffer.retrieve_message(cid) is None


def test_buffer_len(buffer: MessageBuffer):
    assert len(buffer) == 0
    buffer.add_message(m1)
    assert len(buffer) == 1


def test_close(communicator: FakeBaseCommunicator):
    communicator.close()
    assert communicator.socket.closed is True  # type: ignore


def test_context_manager():
    stored_communicator = None
    with FakeBaseCommunicator() as communicator:  # type: ignore
        assert isinstance(communicator, FakeBaseCommunicator)  # assert enter
        stored_communicator = communicator
    assert stored_communicator.socket.closed is True  # exit


def test_send_socket_message(communicator: FakeBaseCommunicator):
    msg = Message(receiver="rec", sender="abc")
    BaseCommunicator._send_socket_message(communicator, msg)
    assert communicator.socket._s == [msg.to_frames()]  # type: ignore


def test_send_message(communicator: FakeBaseCommunicator):
    msg = Message(receiver="rec", sender="")
    communicator.send_message(msg)
    sent = communicator._s.pop()
    assert sent.sender == b"communicator"
    msg.sender = b"communicator"
    assert sent == msg


class Test_sign_in:
    def test_sign_in_successful(self, communicator: FakeBaseCommunicator, fake_cid_generation):
        message = Message(receiver=b"N3.communicator", sender=b"N3.COORDINATOR",
                          conversation_id=cid,
                          message_type=MessageTypes.JSON,
                          data={
                              "id": 0, "result": None, "jsonrpc": "2.0",
                              })
        communicator._r = [message]  # type: ignore
        communicator.namespace = None
        communicator.sign_in()
        assert communicator.namespace == "N3"

    def test_not_valid_message(self, communicator: FakeBaseCommunicator,
                               caplog: pytest.LogCaptureFixture,
                               fake_cid_generation):
        message = Message("communicator", "COORDINATOR", data=b"[]", conversation_id=cid)
        communicator._r = [message]  # type: ignore
        communicator.sign_in()
        caplog.records[-1].msg.startswith("Not json message received:")

    def test_duplicate_name(self, communicator: FakeBaseCommunicator,
                            caplog: pytest.LogCaptureFixture,
                            fake_cid_generation):
        communicator.namespace = None
        message = Message("communicator", "N3.COORDINATOR", message_type=MessageTypes.JSON,
                          data=ErrorResponse(id=5, error=DUPLICATE_NAME),
                          conversation_id=cid)
        communicator._r = [message]  # type: ignore
        communicator.sign_in()
        assert communicator.namespace is None
        assert caplog.records[-1].msg == "Sign in failed, the name is already used."

    def test_handle_unknown_error(self, communicator: FakeBaseCommunicator,
                                  caplog: pytest.LogCaptureFixture,
                                  fake_cid_generation):
        communicator.namespace = None
        message = Message("communicator", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrpc": "2.0", "error": {'code': 123545, "message": "error_msg"}, "id": 5
        }, conversation_id=cid)
        communicator._r = [message]  # type: ignore
        communicator.sign_in()
        assert communicator.namespace is None
        assert caplog.records[-1].msg.startswith("Sign in failed, unknown error")

    def test_handle_request_message(self, communicator: FakeBaseCommunicator,
                                    caplog: pytest.LogCaptureFixture,
                                    fake_cid_generation
                                    ):
        """Handle a message without result or error."""
        communicator.namespace = None
        message = Message("communicator", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrpc": "2.0", "id": 5, "method": "some_method",
        }, conversation_id=cid)
        communicator._r = [message]  # type: ignore
        communicator.sign_in()
        assert communicator.namespace is None
        assert caplog.records[-1].msg.startswith("Sign in failed, unknown error")

    def test_log_timeout_error(self, communicator: FakeBaseCommunicator,
                               caplog: pytest.LogCaptureFixture):
        communicator.sign_in()
        assert caplog.records[-1].msg.startswith("Signing in timed out.")


class Test_finish_sign_in:
    @pytest.fixture
    def communicator_fsi(self, communicator: FakeBaseCommunicator,
                         caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.INFO)
        communicator.finish_sign_in(response_message=Message(
            b"communicator", b"N5.COORDINATOR",
            message_type=MessageTypes.JSON,
            data={"id": 10, "result": None, "jsonrpc": "2.0"}))
        return communicator

    def test_namespace(self, communicator_fsi: FakeBaseCommunicator):
        assert communicator_fsi.namespace == "N5"

    def test_full_name(self, communicator_fsi: FakeBaseCommunicator):
        assert communicator_fsi.full_name == "N5.communicator"

    def test_log_message(self, communicator_fsi: FakeBaseCommunicator,
                         caplog: pytest.LogCaptureFixture):
        assert caplog.get_records("setup")[-1].message == ("Signed in to Node 'N5'.")


def test_heartbeat(communicator: FakeBaseCommunicator):
    communicator.heartbeat()
    msg = communicator._s.pop()
    assert msg.receiver == b"COORDINATOR"
    assert msg.payload == []


def test_sign_out_fail(communicator: FakeBaseCommunicator, caplog: pytest.LogCaptureFixture,
                       fake_cid_generation):
    communicator.namespace = "N3"
    message = Message("communicator", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
        "jsonrpc": "2.0", "error": {"code": 12345}, "id": 1,
    }, conversation_id=cid)
    communicator._r = [message]  # type: ignore
    communicator.sign_out()
    assert communicator.namespace is not None
    assert caplog.messages[-1].startswith("Signing out failed")


def test_sign_out_success(communicator: FakeBaseCommunicator, fake_cid_generation):
    communicator.namespace = "N3"
    message = Message("communicator", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
        "jsonrpc": "2.0", "result": None, "id": 1,
    }, conversation_id=cid)
    communicator._r = [message]  # type: ignore
    communicator.sign_out()
    assert communicator.namespace is None


def test_finish_sign_out(communicator: FakeBaseCommunicator):
    communicator.finish_sign_out()
    assert communicator.namespace is None
    assert communicator.full_name == "communicator"


class Test_read_message:
    conf: list[tuple[list[Message], list[Message], Optional[bytes], list[Message], list[Message],
                     str]] = [
        # socket_in, buffer_in, cid, socket_out, buffer_out, test_id
        # find first not requested message
        ([m1], [], None, [], [], "return first message from socket"),
        ([m2], [m1], None, [m2], [], "return first message from buffer, not socket"),
        ([m1], [mr], None, [], [mr], "ignore requested message in buffer"),
        ([mr, m1], [], None, [], [mr], "ignore requested message in socket"),
        # find requested message
        ([mr], [], cid, [], [], "return specific message from socket"),
        ([m2], [mr], cid, [m2], [], "return specific message from buffer"),
        ([mr], [m2], cid, [], [m2], "return specific message from socket although filled buffer"),
        ([m2, mr, m1], [], cid, [m1], [m2], "find specific message in socket"),
        ([], [m2, mr, m1], cid, [], [m2, m1], "find specific message in buffer"),
    ]
    ids = [test[-1] for test in conf]

    def test_return_message_from_socket(self, communicator: FakeBaseCommunicator):
        communicator._r = [m1]  # type: ignore
        assert communicator.read_message() == m1

    def test_return_message_from_buffer(self, communicator: FakeBaseCommunicator):
        communicator.message_buffer.add_message(m1)
        assert communicator.read_message() == m1
        # assert that no error is raised

    def test_cid_not_longer_in_requested_ids(self, communicator: FakeBaseCommunicator):
        communicator.message_buffer.add_conversation_id(cid)
        communicator.message_buffer.add_message(mr)
        communicator.read_message(conversation_id=cid)
        assert communicator.message_buffer.is_conversation_id_requested(cid) is False

    @pytest.mark.parametrize("test", conf, ids=ids)
    def test_return_correct_message(self,
                                    test: tuple[list[Message], list[Message], Optional[bytes]],
                                    communicator: FakeBaseCommunicator):
        socket, buffer, cid0, *_ = test
        communicator._r = socket.copy()  # type: ignore
        for m in buffer:
            communicator.message_buffer.add_message(m)
        communicator.message_buffer.add_conversation_id(cid)
        # act
        result = communicator.read_message(conversation_id=cid0)
        assert result == m1 if cid is None else mr

    @pytest.mark.parametrize("test", conf, ids=ids)
    def test_correct_buffer_socket(self,
                                   test: tuple[list[Message], list[Message], Optional[bytes],
                                               list[Message], list[Message]],
                                   communicator: FakeBaseCommunicator):
        socket_in, buffer_in, cid0, socket_out, buffer_out, *_ = test
        communicator._r = socket_in.copy()  # type: ignore
        for m in buffer_in:
            communicator.message_buffer.add_message(m)
        communicator.message_buffer.add_conversation_id(cid)
        # act
        communicator.read_message(conversation_id=cid0)
        assert communicator._r == socket_out  # type: ignore
        assert communicator.message_buffer._messages == buffer_out

    def test_timeout_zero_works(self, communicator: FakeBaseCommunicator):
        communicator._r = [m1]  # type: ignore
        communicator.read_message(timeout=0)
        # assert that no error is raised

    def test_timeout_error(self, communicator: FakeBaseCommunicator):
        def waiting(*args, **kwargs):
            time.sleep(.1)
            return m1
        communicator._read_socket_message = waiting  # type: ignore[assignment]
        with pytest.raises(TimeoutError):
            communicator.read_message(conversation_id=cid, timeout=0)


class Test_ask_message:
    expected_sent = Message("receiver", sender="communicator", conversation_id=cid)
    expected_response = Message("communicator", sender="receiver", conversation_id=cid)

    @pytest.fixture
    def communicator_asked(self, communicator: FakeBaseCommunicator):
        communicator._r = [self.expected_response]  # type: ignore
        self.response = communicator.ask_message(message=self.expected_sent)
        return communicator

    def test_sent_expected(self, communicator_asked: FakeBaseCommunicator):
        assert communicator_asked._s == [self.expected_sent]

    def test_expected_response(self, communicator_asked):
        assert self.expected_response == self.response

    def test_no_cid_in_requested_cids_list(self, communicator_asked: FakeBaseCommunicator):
        assert communicator_asked.message_buffer.is_conversation_id_requested(cid) is False


class Test_handle_not_signed_in:
    @pytest.fixture
    def communicator_hnsi(self, communicator: FakeBaseCommunicator) -> FakeBaseCommunicator:
        communicator.namespace = "xyz"
        communicator.sign_in = MagicMock()  # type: ignore
        communicator.handle_not_signed_in()
        communicator.sign_in.assert_called_once
        return communicator

    def test_namespace_reset(self, communicator_hnsi: FakeBaseCommunicator):
        assert communicator_hnsi.namespace is None

    def test_sign_in_called(self, communicator_hnsi: FakeBaseCommunicator):
        communicator_hnsi.sign_in.assert_called_once()  # type: ignore

    def test_log_warning(self, communicator_hnsi: FakeBaseCommunicator,
                         caplog: pytest.LogCaptureFixture) -> None:
        assert caplog.get_records(when="setup")[-1].message == "I was not signed in, signing in."
