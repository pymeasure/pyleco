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
from unittest.mock import MagicMock
import time
from typing import Optional

import pytest

from pyleco.core import VERSION_B
from pyleco.core.message import Message, MessageTypes
from pyleco.core.leco_protocols import ExtendedComponentProtocol, LogLevels
from pyleco.core.internal_protocols import CommunicatorProtocol
from pyleco.core.serialization import serialize_data
from pyleco.test import FakeContext, FakePoller
from pyleco.json_utils.json_objects import Request, ResultResponse, ErrorResponse
from pyleco.json_utils.errors import JSONRPCError, INVALID_REQUEST, NOT_SIGNED_IN, DUPLICATE_NAME,\
    NODE_UNKNOWN, RECEIVER_UNKNOWN

from pyleco.utils.message_handler import MessageHandler, SimpleEvent


handler_name = "N1.handler"
remote_name = "remote"
cid = b"conversation_id;"
header = b"".join((cid, b"\x00" * 4))


def fake_generate_cid():
    return cid


@pytest.fixture()
def fake_cid_generation(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


@pytest.fixture()
def handler() -> MessageHandler:
    handler = MessageHandler(name=handler_name.split(".")[1], context=FakeContext())  # type: ignore
    handler.namespace = handler_name.split(".")[0]
    handler.stop_event = SimpleEvent()
    handler.timeout = 0.1
    return handler


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(ExtendedComponentProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: ExtendedComponentProtocol):
            pass
        testing(MessageHandler(name="test"))

        def test_internal_communicator_protocol(communicator: CommunicatorProtocol):
            pass
        test_internal_communicator_protocol(MessageHandler(name="test"))

    @pytest.fixture
    def component_methods(self, handler: MessageHandler):
        response = handler.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}')
        result = handler.rpc_generator.get_result_from_response(response)  # type: ignore
        return result.get('methods')

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(self, component_methods, method):
        for m in component_methods:
            if m.get('name') == method:
                return
        raise AssertionError(f"Method {method} is not available.")


class Test_setup_logging:
    def test(self, handler: MessageHandler):
        logger = logging.getLogger("test")
        logger.addHandler(logging.NullHandler())
        handler.setup_logging(logger)
        assert len(logger.handlers) == 2
        assert handler.root_logger == logger
        assert handler.log == logging.getLogger("test.MessageHandler")


class Test_namespace_setter:
    def test_full_name_without_namespace(self, handler: MessageHandler):
        handler.namespace = None
        assert handler.full_name == "handler"

    @pytest.fixture
    def handler_ns(self, handler: MessageHandler) -> MessageHandler:
        handler.namespace = "xyz"
        return handler

    def test_namespace(self, handler_ns: MessageHandler):
        assert handler_ns.namespace == "xyz"

    def test_full_name(self, handler_ns: MessageHandler):
        assert handler_ns.full_name == "xyz.handler"

    def test_rpc_title(self, handler_ns: MessageHandler):
        assert handler_ns.rpc.title == "xyz.handler"

    def test_log_handler(self, handler_ns: MessageHandler):
        assert handler_ns.log_handler.full_name == "xyz.handler"


class Test_sign_in:
    def test_sign_in_successful(self, handler: MessageHandler, fake_cid_generation):
        message = Message(receiver=b"N3.handler", sender=b"N3.COORDINATOR",
                          conversation_id=cid,
                          message_type=MessageTypes.JSON,
                          data={
                              "id": 0, "result": None, "jsonrpc": "2.0",
                              })
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.namespace = None
        handler.sign_in()
        assert handler.namespace == "N3"

    def test_not_valid_message(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture,
                               fake_cid_generation):
        message = Message("handler", "COORDINATOR", data=b"[]", conversation_id=cid)
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.sign_in()
        caplog.records[-1].msg.startswith("Not json message received:")

    def test_duplicate_name(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture,
                            fake_cid_generation):
        handler.namespace = None
        message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON,
                          data=ErrorResponse(id=5, error=DUPLICATE_NAME),
                          conversation_id=cid)
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.sign_in()
        assert handler.namespace is None
        assert caplog.records[-1].msg == "Sign in failed, the name is already used."

    def test_handle_unknown_error(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture,
                                  fake_cid_generation):
        handler.namespace = None
        message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrpc": "2.0", "error": {'code': 123545, "message": "error_msg"}, "id": 5
        }, conversation_id=cid)
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.sign_in()
        assert handler.namespace is None
        assert caplog.records[-1].msg.startswith("Sign in failed, unknown error")

    def test_handle_request_message(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture,
                                    fake_cid_generation
                                    ):
        """Handle a message without result or error."""
        handler.namespace = None
        message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrpc": "2.0", "id": 5, "method": "some_method",
        }, conversation_id=cid)
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.sign_in()
        assert handler.namespace is None
        assert caplog.records[-1].msg.startswith("Sign in failed, unknown error")

    def test_log_timeout_error(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture):
        handler.sign_in()
        assert caplog.records[-1].msg.startswith("Signing in timed out.")


class Test_finish_sign_in:
    @pytest.fixture
    def handler_fsi(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture):
        caplog.set_level(logging.INFO)
        handler.finish_sign_in(response_message=Message(
            b"handler", b"N5.COORDINATOR",
            message_type=MessageTypes.JSON,
            data={"id": 10, "result": None, "jsonrpc": "2.0"}))
        return handler

    def test_namespace(self, handler_fsi: MessageHandler):
        assert handler_fsi.namespace == "N5"

    def test_full_name(self, handler_fsi: MessageHandler):
        assert handler_fsi.full_name == "N5.handler"

    def test_log_message(self, handler_fsi: MessageHandler, caplog: pytest.LogCaptureFixture):
        assert caplog.get_records("setup")[-1].message == ("Signed in to Node 'N5'.")


def test_sign_out_fail(handler: MessageHandler, caplog: pytest.LogCaptureFixture,
                       fake_cid_generation):
    handler.namespace = "N3"
    message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
        "jsonrpc": "2.0", "error": {"code": 12345}, "id": 1,
    }, conversation_id=cid)
    handler.socket._r = [message.to_frames()]  # type: ignore
    handler.sign_out()
    assert handler.namespace is not None
    assert caplog.messages[-1].startswith("Signing out failed")


def test_sign_out_success(handler: MessageHandler, fake_cid_generation):
    handler.namespace = "N3"
    message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
        "jsonrpc": "2.0", "result": None, "id": 1,
    }, conversation_id=cid)
    handler.socket._r = [message.to_frames()]  # type: ignore
    handler.sign_out()
    assert handler.namespace is None


def test_finish_sign_out(handler: MessageHandler):
    handler.finish_sign_out()
    assert handler.namespace is None
    assert handler.full_name == "handler"


# test communication
def test_send(handler: MessageHandler):
    handler.send("N2.CB", conversation_id=cid, message_id=b"sen", data=[["TEST"]],
                 message_type=MessageTypes.JSON)
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"N1.handler", b"conversation_id;sen\x01",
                                  b'[["TEST"]]']]


def test_send_with_sender(handler: MessageHandler):
    handler.send("N2.CB", sender="sender", conversation_id=cid, message_id=b"sen",
                 data=[["TEST"]],
                 message_type=MessageTypes.JSON)
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"sender", b"conversation_id;sen\x01",
                                  b'[["TEST"]]']]


def test_send_message_raises_error(handler: MessageHandler, caplog: pytest.LogCaptureFixture):
    handler.send(receiver=remote_name, header=b"header", conversation_id=b"12345")
    assert caplog.messages[-1].startswith("Composing message with")


def test_heartbeat(handler: MessageHandler, fake_cid_generation):
    handler.heartbeat()
    assert handler.socket._s == [[VERSION_B, b"COORDINATOR", b"N1.handler", header]]


class Test_read_message:
    m1 = Message(receiver=handler_name, sender="xy")  # some message
    mr = Message(receiver=handler_name, sender="xy", conversation_id=cid)  # requested message
    m2 = Message(receiver=handler_name, sender="xy")  # another message

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

    def test_return_message_from_socket(self, handler: MessageHandler):
        handler.socket._r = [self.m1.to_frames()]  # type: ignore
        assert handler.read_message() == self.m1

    def test_return_message_from_buffer(self, handler: MessageHandler):
        handler.message_buffer.add_message(self.m1)
        assert handler.read_message() == self.m1
        # assert that no error is raised

    def test_cid_not_longer_in_requested_ids(self, handler: MessageHandler):
        handler.message_buffer.add_conversation_id(cid)
        handler.message_buffer.add_message(self.mr)
        handler.read_message(conversation_id=cid)
        assert handler.message_buffer.is_conversation_id_requested(cid) is False

    @pytest.mark.parametrize("test", conf, ids=ids)
    def test_return_correct_message(self,
                                    test: tuple[list[Message], list, Optional[bytes]],
                                    handler: MessageHandler):
        socket, buffer, cid0, *_ = test
        handler.socket._r = [m.to_frames() for m in socket]  # type: ignore
        for m in buffer:
            handler.message_buffer.add_message(m)
        handler.message_buffer.add_conversation_id(cid)
        # act and assert
        assert handler.read_message(conversation_id=cid0) == self.m1 if cid is None else self.mr

    @pytest.mark.parametrize("test", conf, ids=ids)
    def test_correct_buffer_socket(self, test, handler: MessageHandler):
        socket_in, buffer_in, cid0, socket_out, buffer_out, *_ = test
        handler.socket._r = [m.to_frames() for m in socket_in]  # type: ignore
        for m in buffer_in:
            handler.message_buffer.add_message(m)
        handler.message_buffer.add_conversation_id(cid)
        # act
        handler.read_message(conversation_id=cid0)
        assert handler.socket._r == [m.to_frames() for m in socket_out]  # type: ignore
        assert handler.message_buffer._messages == buffer_out

    def test_timeout_zero_works(self, handler: MessageHandler):
        handler.socket._r = [self.m1.to_frames()]  # type: ignore
        handler.read_message(timeout=0)
        # assert that no error is raised

    def test_timeout_error(self, handler: MessageHandler):
        def waiting(*args, **kwargs):
            time.sleep(.1)
            return self.m1
        handler._read_socket_message = waiting  # type: ignore[assignment]
        with pytest.raises(TimeoutError):
            handler.read_message(conversation_id=cid, timeout=0)


class Test_ask_message:
    expected_sent = Message(remote_name, sender=handler_name, conversation_id=cid)
    expected_response = Message(handler_name, sender=remote_name, conversation_id=cid)

    @pytest.fixture
    def handler_asked(self, handler: MessageHandler):
        handler.socket._r = [self.expected_response.to_frames()]  # type: ignore
        self.response = handler.ask_message(message=self.expected_sent)
        return handler

    def test_sent_expected(self, handler_asked: MessageHandler):
        assert handler_asked.socket._s == [self.expected_sent.to_frames()]

    def test_expected_response(self, handler_asked):
        assert self.expected_response == self.response

    def test_no_cid_in_requested_cids_list(self, handler_asked: MessageHandler):
        assert handler_asked.message_buffer.is_conversation_id_requested(cid) is False


class Test_read_and_handle_message:
    def test_handle_message_handles_no_new_socket_message(self, handler: MessageHandler):
        """Test, that the message handler does not raise an error without a new socket message."""
        handler.message_buffer.add_conversation_id(cid)
        handler.socket._r = [  # type: ignore
            Message(receiver=handler_name, sender=remote_name, conversation_id=cid).to_frames()]
        # act
        handler.read_and_handle_message()
        # assert that no error is raised.

    def test_handle_message_ignores_heartbeats(self, handler: MessageHandler):
        handler.handle_message = MagicMock()  # type: ignore
        # empty message of heartbeat
        handler.socket._r = [[VERSION_B, b"N1.handler", b"whatever", b";"]]  # type: ignore
        handler.read_and_handle_message()
        handler.handle_message.assert_not_called()

    @pytest.mark.parametrize("i, out", (
        (  # shutdown
         [VERSION_B, b"N1.handler", b"N1.CB", b"conversation_id;mid" + bytes((MessageTypes.JSON,)),
          serialize_data({"id": 5, "method": "shut_down", "jsonrpc": "2.0"})],
         [VERSION_B, b"N1.CB", b"N1.handler", b"conversation_id;\x00\x00\x00\x00",
          serialize_data({"id": 5, "result": None, "jsonrpc": "2.0"})]),
        (  # pong
         Message("N1.handler", "N1.COORDINATOR", conversation_id=cid,
                 message_type=MessageTypes.JSON, data=Request(id=2, method="pong")
                 ).to_frames(),
         Message("N1.COORDINATOR", "N1.handler", conversation_id=cid,
                 message_type=MessageTypes.JSON,
                 data=ResultResponse(id=2, result=None)).to_frames()),
    ))
    def test_read_and_handle_message(self, handler: MessageHandler,
                                     i: list[bytes], out: list[bytes]):
        handler.socket._r = [i]  # type: ignore
        handler.read_and_handle_message()
        for j in range(len(out)):
            if j == 3:
                continue  # reply adds timestamp
            assert handler.socket._s[0][j] == out[j]  # type: ignore

    def test_handle_not_signed_in_message(self, handler: MessageHandler):
        handler.sign_in = MagicMock()  # type: ignore
        handler.socket._r = [Message(receiver="handler", sender="N1.COORDINATOR",  # type: ignore
                                     message_type=MessageTypes.JSON,
                                     data=ErrorResponse(id=5, error=NOT_SIGNED_IN),
                                     ).to_frames()]
        handler.read_and_handle_message()
        assert handler.namespace is None
        handler.sign_in.assert_called_once()
        assert handler.full_name == "handler"

    def test_handle_node_unknown_message(self, handler: MessageHandler):
        error = Message("N1.handler", "N1.COORDINATOR", message_type=MessageTypes.JSON,
                        data=ErrorResponse(id=None, error=NODE_UNKNOWN))
        handler.message_buffer.add_message(error)
        handler.read_and_handle_message()
        # assert that no error is raised and that no message is sent
        assert handler.socket._s == []

    def test_handle_receiver_unknown_message(self, handler: MessageHandler):
        error = Message("N1.handler", "N1.COORDINATOR", message_type=MessageTypes.JSON,
                        data=ErrorResponse(id=None, error=RECEIVER_UNKNOWN))
        handler.message_buffer.add_message(error)
        handler.read_and_handle_message()
        # assert that no error is raised and that no message is sent
        assert handler.socket._s == []

    def test_handle_ACK_does_not_change_Namespace(self, handler: MessageHandler):
        """Test that an ACK does not change the Namespace, if it is already set."""
        handler.socket._r = [Message(b"N3.handler", b"N3.COORDINATOR",  # type: ignore
                                     message_type=MessageTypes.JSON,
                                     data={"id": 3, "result": None, "jsonrpc": "2.0"}).to_frames()]
        handler.namespace = "N1"
        handler.read_and_handle_message()
        assert handler.namespace == "N1"

    def test_handle_invalid_json_message(self, handler: MessageHandler,
                                         caplog: pytest.LogCaptureFixture):
        """An invalid message should not cause the message handler to crash."""
        handler.socket._r = [Message(b"N3.handler", b"N3.COORDINATOR",  # type: ignore
                                     message_type=MessageTypes.JSON,
                                     data={"without": "method..."}).to_frames()]
        handler.read_and_handle_message()
        assert caplog.records[-1].msg.startswith("Invalid JSON message")

    def test_handle_corrupted_message(self, handler: MessageHandler,
                                      caplog: pytest.LogCaptureFixture):
        """An invalid message should not cause the message handler to crash."""
        handler.socket._r = [Message(b"N3.handler", b"N3.COORDINATOR",  # type: ignore
                                     message_type=MessageTypes.JSON,
                                     data=[]).to_frames()]
        handler.read_and_handle_message()
        assert caplog.records[-1].msg.startswith("Invalid JSON message")

    def test_handle_undecodable_message(self, handler: MessageHandler,
                                        caplog: pytest.LogCaptureFixture):
        """An invalid message should not cause the message handler to crash."""
        message = Message(
            b"N3.handler",
            b"N3.COORDINATOR",
            message_type=MessageTypes.JSON,
            additional_payload=[b"()"],
        )
        handler.socket._r = [message.to_frames()]  # type: ignore
        handler.read_and_handle_message()
        assert caplog.records[-1].msg.startswith("Could not decode")


def test_handle_unknown_message_type(handler: MessageHandler, caplog: pytest.LogCaptureFixture):
    message = Message(handler_name, sender="sender", message_type=255)
    handler.handle_message(message=message)
    assert caplog.records[-1].message.startswith("Message from b'sender'")


class Test_process_json_message:
    def test_handle_rpc_request(self, handler: MessageHandler):
        message = Message(receiver=handler_name, sender=remote_name,
                          data=Request(id=5, method="pong"),
                          conversation_id=cid, message_type=MessageTypes.JSON)
        response = Message(receiver=remote_name,
                           data=ResultResponse(id=5, result=None),
                           conversation_id=cid, message_type=MessageTypes.JSON)
        result = handler.process_json_message(message=message)
        assert result == response

    def test_handle_json_not_request(self, handler: MessageHandler):
        """Test, that a json message, which is not a request, is handled appropriately."""
        data = ResultResponse(id=5, result=None)  # some json, which is not a request.
        message = Message(receiver=handler_name, sender=remote_name,
                          data=data,
                          conversation_id=cid, message_type=MessageTypes.JSON)
        result = handler.process_json_message(message=message)
        assert result.receiver == remote_name.encode()
        assert result.conversation_id == cid
        assert result.header_elements.message_type == MessageTypes.JSON
        with pytest.raises(JSONRPCError) as exc_info:
            handler.rpc_generator.get_result_from_response(result.data)  # type: ignore
        error = exc_info.value.rpc_error
        assert error.code == INVALID_REQUEST.code
        assert error.message == INVALID_REQUEST.message


class Test_process_json_message_with_created_binary:
    payload_in: list[bytes]
    payload_out: list[bytes]

    @pytest.fixture(
        params=(
            # normally created binary method
            {"method": "do_binary", "params": [5]},  # with a list
            {"method": "do_binary", "params": {"data": 5}},  # a dictionary
            # manually created binary method
            {"method": "do_binary_manually", "params": [5]},
            {"method": "do_binary_manually", "params": {"data": 5}},
        ),
        ids=(
            "created, list",
            "created, dict",
            "manual, list",
            "manual, dict",
        ),
    )
    def data(self, request):
        """Create a request with a list and a dict of other parameters."""
        d = {"jsonrpc": "2.0", "id": 8}
        d.update(request.param)
        return d

    @pytest.fixture
    def handler_b(self, handler: MessageHandler):
        test_class = self
        class SpecialHandler(MessageHandler):
            def do_binary_manually(self, data: int) -> int:
                test_class.payload_in = self.current_message.payload[1:]
                self.additional_response_payload = test_class.payload_out
                return data

            def do_binary(
                self, data: int, additional_payload: Optional[list[bytes]] = None
            ) -> tuple[int, list[bytes]]:
                test_class.payload_in = additional_payload  # type: ignore
                return data, test_class.payload_out

        handler = SpecialHandler(name=handler_name.split(".")[1], context=FakeContext())  # type: ignore
        handler.namespace = handler_name.split(".")[0]
        handler.stop_event = SimpleEvent()
        handler.timeout = 0.1

        handler.register_rpc_method(handler.do_binary_manually)
        handler.register_binary_rpc_method(
            handler.do_binary, accept_binary_input=True, return_binary_output=True
        )
        return handler

    def test_message_stored(self, handler_b: MessageHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        handler_b.process_json_message(m_in)
        assert handler_b.current_message == m_in

    def test_empty_additional_payload(self, handler_b: MessageHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        handler_b.process_json_message(m_in)
        assert handler_b.additional_response_payload is None

    def test_binary_payload_available(self, handler_b: MessageHandler, data):
        m_in = Message(
            "abc", data=data, message_type=MessageTypes.JSON, additional_payload=[b"def"]
        )
        self.payload_out = []
        handler_b.process_json_message(m_in)
        assert self.payload_in == [b"def"]

    def test_binary_payload_sent(self, handler_b: MessageHandler, data):
        m_in = Message("abc", data=data, message_type=MessageTypes.JSON)
        self.payload_out = [b"ghi"]
        response = handler_b.process_json_message(m_in)
        assert response.payload[1:] == [b"ghi"]
        assert response.data == {"jsonrpc": "2.0", "id": 8, "result": 5}


def test_handle_binary_return_value(handler: MessageHandler):
    payload = [b"abc", b"def"]
    result = handler._handle_binary_return_value((None, payload))
    assert result is None
    assert handler.additional_response_payload == payload


class Test_generate_binary_method:
    @pytest.fixture
    def binary_method(self):
        def binary_method(index: int, additional_payload: list[bytes]) -> tuple[None, list[bytes]]:
            """Docstring of binary method."""
            return None, [additional_payload[index]]
        return binary_method

    @pytest.fixture(params=(True, False))
    def modified_binary_method(self, handler: MessageHandler, binary_method, request):
        handler.current_message = Message(
            "rec", "send", data=b"", additional_payload=[b"0", b"1", b"2", b"3"]
        )
        self._accept_binary_input = request.param
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=self._accept_binary_input, return_binary_output=True
        )
        self.handler = handler
        return mod

    def test_name(self, binary_method, modified_binary_method):
        assert modified_binary_method.__name__ == binary_method.__name__

    def test_docstring(self, modified_binary_method, binary_method):
        doc_addition = (
            "(binary input output method)"
            if self._accept_binary_input
            else "(binary output method)"
        )
        assert modified_binary_method.__doc__ == binary_method.__doc__ + "\n" + doc_addition

    @pytest.mark.parametrize(
        "input, output, string",
        (
            (False, False, "(binary method)"),
            (True, False, "(binary input method)"),
            (False, True, "(binary output method)"),
            (True, True, "(binary input output method)"),
        ),
    )
    def test_docstring_without_original_docstring(
        self, handler: MessageHandler, input, output, string
    ):
        def binary_method(additional_payload):
            return 7
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=input, return_binary_output=output
        )
        assert mod.__doc__ == string

    def test_annotation(self, modified_binary_method, binary_method):
        assert modified_binary_method.__annotations__ == binary_method.__annotations__

    def test_functionality_kwargs(self, modified_binary_method):
        if self._accept_binary_input:
            assert modified_binary_method(index=1) is None
        else:
            assert (
                modified_binary_method(index=1, additional_payload=[b"0", b"1", b"2", b"3"]) is None
            )
        assert self.handler.additional_response_payload == [b"1"]

    def test_functionality_args(self, modified_binary_method):
        if self._accept_binary_input:
            assert modified_binary_method(1) is None
        else:
            assert modified_binary_method(1, [b"0", b"1", b"2", b"3"]) is None
        assert self.handler.additional_response_payload == [b"1"]

    def test_binary_input_from_message(self, handler: MessageHandler):
        handler.current_message = Message("rec", "send", data=b"", additional_payload=[b"0"])

        def binary_method(additional_payload = None):
            return 7
        mod = handler._generate_binary_capable_method(
            binary_method, accept_binary_input=True, return_binary_output=False
        )
        assert mod() == 7


class Test_listen:
    @pytest.fixture
    def handler_l(self, handler: MessageHandler, fake_cid_generation):
        event = SimpleEvent()
        event.set()
        handler.socket._r = [  # type: ignore
            Message("handler", "N1.COORDINATOR", message_type=MessageTypes.JSON,
                    conversation_id=cid,
                    data={"id": 2, "result": None, "jsonrpc": "2.0"}).to_frames()]
        handler.listen(stop_event=event)
        return handler

    def test_messages_are_sent(self, handler_l: MessageHandler):
        assert handler_l.socket._s == [
            Message("COORDINATOR", "N1.handler", conversation_id=cid,
                    message_type=MessageTypes.JSON,
                    data={"id": 1, "method": "sign_in", "jsonrpc": "2.0"}).to_frames(),
            Message("COORDINATOR", "N1.handler", conversation_id=cid,
                    message_type=MessageTypes.JSON,
                    data={"id": 2, "method": "sign_out", "jsonrpc": "2.0"}).to_frames(),
        ]

    def test_next_beat(self, handler_l: MessageHandler):
        assert handler_l.next_beat > 0

    def test_loop_element_changes_heartbeat(self, handler_l: MessageHandler):
        handler_l.next_beat = 0
        # Act
        handler_l._listen_loop_element(poller=FakePoller(), waiting_time=0)  # type: ignore
        assert handler_l.next_beat > 0

    def test_loop_element_does_not_change_heartbeat_if_short(self, handler_l: MessageHandler):
        handler_l.next_beat = float("inf")
        # Act
        handler_l._listen_loop_element(poller=FakePoller(), waiting_time=0)  # type: ignore
        assert handler_l.next_beat == float("inf")

    def test_KeyboardInterrupt_in_loop(self, handler: MessageHandler):
        def raise_error(poller, waiting_time):
            raise KeyboardInterrupt
        handler.sign_in = MagicMock()  # type: ignore[method-assign]
        handler._listen_loop_element = raise_error  # type: ignore
        handler.listen()
        # assert that no error is raised and that the test does not hang


def test_listen_loop_element(handler: MessageHandler):
    poller = FakePoller()
    poller.register(handler.socket)
    handler.socket._r = [  # type: ignore
        Message("Test", "COORDINATOR").to_frames()
    ]
    socks = handler._listen_loop_element(poller, 0)  # type: ignore
    assert socks == {}


class Test_listen_close:
    @pytest.fixture
    def handler_lc(self, handler: MessageHandler):
        handler._listen_close(0)
        return handler

    def test_sign_out_sent(self, handler_lc: MessageHandler):
        sent = Message.from_frames(*handler_lc.socket._s[-1])  # type: ignore
        assert handler_lc.socket._s == [Message("COORDINATOR", "N1.handler",
                                                conversation_id=sent.conversation_id,
                                                message_type=MessageTypes.JSON,
                                                data={
                                                    "id": 1, "method": "sign_out", "jsonrpc": "2.0",
                                                    },
                                                ).to_frames()]

    def test_warning_log_written(self, handler_lc: MessageHandler,
                                 caplog: pytest.LogCaptureFixture):
        assert caplog.get_records("setup")[-1].message == "Waiting for sign out response timed out."


def test_set_log_level(handler: MessageHandler):
    handler.set_log_level(LogLevels.ERROR)
    assert handler.root_logger.level == 40  # logging.ERROR


def test_shutdown(handler: MessageHandler):
    handler.stop_event = SimpleEvent()
    handler.shut_down()
    assert handler.stop_event.is_set() is True
