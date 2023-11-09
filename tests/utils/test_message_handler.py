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

from unittest.mock import MagicMock

import pytest

from pyleco.core import VERSION_B
from pyleco.core.message import Message, MessageTypes
from pyleco.core.leco_protocols import ExtendedComponentProtocol, LogLevels
from pyleco.core.serialization import serialize_data
from pyleco.test import FakeContext, FakePoller
from pyleco.errors import NOT_SIGNED_IN, DUPLICATE_NAME

from pyleco.utils.message_handler import MessageHandler, SimpleEvent


cid = b"conversation_id;"
header = b"".join((cid, b"\x00" * 4))


def fake_generate_cid():
    return cid


@pytest.fixture()
def fake_cid_generation(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


@pytest.fixture()
def handler() -> MessageHandler:
    handler = MessageHandler(name="handler", context=FakeContext())  # type: ignore
    handler.namespace = "N1"
    handler.full_name = "N1.handler"
    handler.stop_event = SimpleEvent()
    return handler


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(ExtendedComponentProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: ExtendedComponentProtocol):
            pass
        testing(MessageHandler(name="test"))

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


def test_context_manager():
    stored_handler = None
    with MessageHandler(name="handler", context=FakeContext()) as handler:  # type: ignore
        assert isinstance(handler, MessageHandler)  # assert enter
        stored_handler = handler
    assert stored_handler.socket.closed is True  # exit


def test_finish_sign_in(handler: MessageHandler):
    handler.finish_sign_in(message=Message(b"handler", b"N5.COORDINATOR",
                                           message_type=MessageTypes.JSON, data={
                                               "id": 10, "result": None, "jsonrpc": "2.0"}))
    assert handler.namespace == "N5"
    assert handler.full_name == "N5.handler"


def test_finish_sign_out(handler: MessageHandler):
    handler.finish_sign_out(message=Message(b"handler", b"N5.COORDINATOR",
                                            message_type=MessageTypes.JSON, data={
                                                "id": 10, "result": None, "jsonrpc": "2.0"}))
    assert handler.namespace is None
    assert handler.full_name == "handler"


# test communication
def test_send(handler: MessageHandler):
    handler.send("N2.CB", conversation_id=cid, message_id=b"sen", data=[["TEST"]],
                 message_type=MessageTypes.JSON)
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"N1.handler", b"conversation_id;sen\x01",
                                  b'[["TEST"]]']]


def test_heartbeat(handler: MessageHandler, fake_cid_generation):
    handler.heartbeat()
    assert handler.socket._s == [[VERSION_B, b"COORDINATOR", b"N1.handler", header]]


def test_handle_message_ignores_heartbeats(handler: MessageHandler):
    handler.handle_commands = MagicMock()  # type: ignore
    # empty message of heartbeat
    handler.socket._r = [[VERSION_B, b"N1.handler", b"whatever", b";"]]  # type: ignore
    handler.handle_message()
    handler.handle_commands.assert_not_called()


@pytest.mark.parametrize("i, out", (
    ([VERSION_B, b"N1.handler", b"N1.CB", b"conversation_id;mid;0",
      serialize_data({"id": 5, "method": "shut_down", "jsonrpc": "2.0"})],
     [VERSION_B, b"N1.CB", b"N1.handler", b"conversation_id;\x00\x00\x00\x00",
      serialize_data({"id": 5, "result": None, "jsonrpc": "2.0"})]),
))
def test_handle_message(handler: MessageHandler, i, out):
    handler.socket._r = [i]  # type: ignore
    handler.handle_message()
    for j in range(len(out)):
        if j == 3:
            continue  # reply adds timestamp
        assert handler.socket._s[0][j] == out[j]  # type: ignore


def test_handle_not_signed_in_message(handler: MessageHandler):
    handler.sign_in = MagicMock()  # type: ignore
    handler.socket._r = [Message(receiver="handler", sender="N1.COORDINATOR",  # type: ignore
                                 message_type=MessageTypes.JSON,
                                 data={"id": 5, "error": {"code": NOT_SIGNED_IN.code}}
                                 ).to_frames()]
    handler.handle_message()
    assert handler.namespace is None
    handler.sign_in.assert_called_once()
    assert handler.full_name == "handler"


def test_handle_SIGNIN_message_response(handler: MessageHandler):
    handler._requests[b"conversation_si;"] = "sign_in"
    handler.socket._r = [Message(receiver=b"N3.handler", sender=b"N3.COORDINATOR",  # type: ignore
                                 conversation_id=b"conversation_si;",
                                 message_type=MessageTypes.JSON,
                                 data={
                                     "id": 0, "result": None, "jsonrpc": "2.0",
                                 }).to_frames()]
    handler.namespace = None
    handler.handle_message()
    assert handler.namespace == "N3"


def test_handle_ACK_does_not_change_Namespace(handler: MessageHandler):
    """Test that an ACK does not change the Namespace, if it is already set."""
    handler.socket._r = [Message(b"N3.handler", b"N3.COORDINATOR",  # type: ignore
                                 message_type=MessageTypes.JSON,
                                 data={"id": 3, "result": None, "jsonrpc": "2.0"}).to_frames()]
    handler.namespace = "N1"
    handler.handle_message()
    assert handler.namespace == "N1"


def test_handle_corrupted_message(handler: MessageHandler, caplog: pytest.LogCaptureFixture):
    handler.socket._r = [Message(b"N3.handler", b"N3.COORDINATOR",  # type: ignore
                                 message_type=MessageTypes.JSON,
                                 data=[]).to_frames()]
    handler.handle_message()
    assert caplog.records[-1].msg.startswith("Message data")


class Test_HandleSignInResponses:
    def test_not_valid_message(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture):
        message = Message("handler", "COORDINATOR", data=b"[]")
        handler.handle_sign_in_response(message)
        caplog.records[-1].msg.startswith("Not json message received:")

    def test_sign_in_successful(self, handler: MessageHandler):
        handler.namespace = None
        message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrcpc": "2.0", "result": None, "id": 1,
        })
        handler.handle_sign_in_response(message)
        assert handler.namespace == "N3"

    def test_duplicate_name(self, handler: MessageHandler, caplog: pytest.LogCaptureFixture):
        handler.namespace = None
        message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
            "jsonrpc": "2.0", "error": {'code': DUPLICATE_NAME.code}, "id": 5
        })
        handler.handle_sign_in_response(message=message)
        assert handler.namespace is None
        assert caplog.records[-1].msg == "Sign in failed, the name is already used."


def test_handle_sign_out_response(handler: MessageHandler):
    handler.namespace = "N3"
    message = Message("handler", "N3.COORDINATOR", message_type=MessageTypes.JSON, data={
        "jsonrpc": "2.0", "result": None, "id": 1,
    })
    handler.handle_sign_out_response(message)
    assert handler.namespace is None


class Test_listen:
    @pytest.fixture
    def handler_l(self, handler: MessageHandler):
        event = SimpleEvent()
        event.set()
        handler.socket._r = [  # type: ignore
            Message("handler", "COORDINATOR", message_type=MessageTypes.JSON,
                    data={"id": 2, "result": None, "jsonrpc": "2.0"}).to_frames()]
        handler.listen(stop_event=event)
        return handler

    def test_messages_are_sent(self, handler_l: MessageHandler):
        cids = tuple(handler_l._requests.keys())
        assert handler_l.socket._s == [
            Message("COORDINATOR", "N1.handler", conversation_id=cids[0],
                    message_type=MessageTypes.JSON,
                    data={"id": 1, "method": "sign_in", "jsonrpc": "2.0"}).to_frames(),
            Message("COORDINATOR", "N1.handler", conversation_id=cids[1],
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
