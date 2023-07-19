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
from pyleco.core.message import Message
from pyleco.core.leco_protocols import ExtendedComponentProtocol
from pyleco.test import FakeContext

from pyleco.utils.message_handler import MessageHandler, SimpleEvent, BaseController


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
        testing(MessageHandler(name="test", context=FakeContext()))  # type: ignore

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
    handler.finish_sign_in(message=Message(b"handler", b"N5.COORDINATOR", data={
        "id": 10, "result": None, "jsonrpc": "2.0"}))
    assert handler.namespace == "N5"
    assert handler.full_name == "N5.handler"


def test_finish_sign_out(handler: MessageHandler):
    handler.finish_sign_out(message=Message(b"handler", b"N5.COORDINATOR", data={
        "id": 10, "result": None, "jsonrpc": "2.0"}))
    assert handler.namespace is None
    assert handler.full_name == "handler"


# test communication
def test_send(handler: MessageHandler):
    handler.send("N2.CB", conversation_id=cid, message_id=b"sen", data=[["TEST"]])
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"N1.handler", b"conversation_id;sen\x00",
                                  b'[["TEST"]]']]


def test_heartbeat(handler: MessageHandler, fake_cid_generation):
    handler.heartbeat()
    assert handler.socket._s == [[VERSION_B, b"COORDINATOR", b"N1.handler", header]]


def test_handle_message_ignores_heartbeats(handler: MessageHandler):
    handler.handle_commands = MagicMock()  # type: ignore
    # empty message of heartbeat
    handler.socket._r = [[VERSION_B, b"N1.handler", b"whatever", b";"]]
    handler.handle_message()
    handler.handle_commands.assert_not_called()


@pytest.mark.parametrize("i, out", (
    ([VERSION_B, b"N1.handler", b"N1.CB", b"conversation_id;mid;0",
      b'{"id": 5, "method": "shut_down", "jsonrpc": "2.0"}'],
     [VERSION_B, b"N1.CB", b"N1.handler", b"conversation_id;\x00\x00\x00\x00",
      b'{"id": 5, "result": null, "jsonrpc": "2.0"}']),
))
def test_handle_message(handler: MessageHandler, i, out):
    handler.socket._r = [i]
    handler.handle_message()
    for j in range(len(out)):
        if j == 3:
            continue  # reply adds timestamp
        assert handler.socket._s[0][j] == out[j]  # type: ignore


def test_handle_SIGNIN_message_response(handler: MessageHandler):
    handler._requests[b"conversation_si;"] = "sign_in"
    handler.socket._r = [Message(receiver=b"N3.handler", sender=b"N3.COORDINATOR",
                                 conversation_id=b"conversation_si;", data={
                                     "id": 0, "result": None, "jsonrpc": "2.0",
                                     }).to_frames()]
    handler.namespace = None
    handler.handle_message()
    assert handler.namespace == "N3"


def test_handle_ACK_does_not_change_Namespace(handler: MessageHandler):
    """Test that an ACK does not change the Namespace, if it is already set."""
    handler.socket._r = [[VERSION_B, b"N3.handler", b"N3.COORDINATOR", b";",
                          b'{"id": 3, "result": null, "jsonrpc": "2.0"}']]
    handler.namespace = "N1"
    handler.handle_message()
    assert handler.namespace == "N1"


class Test_listen:
    @pytest.fixture
    def handler_l(self, handler):
        event = SimpleEvent()
        event.set()
        handler.socket._r = [Message(
            "handler", "COORDINATOR",
            data={"id": 2, "result": None, "jsonrpc": "2.0"}).to_frames()]
        handler.listen(stop_event=event)
        return handler

    def test_messages_are_sent(self, handler_l: MessageHandler):
        cids = tuple(handler_l._requests.keys())
        assert handler_l.socket._s == [
            Message("COORDINATOR", "N1.handler", conversation_id=cids[0],
                    data={"id": 1, "method": "sign_in", "jsonrpc": "2.0"}).to_frames(),
            Message("COORDINATOR", "N1.handler", conversation_id=cids[1],
                    data={"id": 2, "method": "sign_out", "jsonrpc": "2.0"}).to_frames(),
        ]


def test_set_log_level(handler: MessageHandler):
    handler.set_log_level(35)
    assert handler.root_logger.level == 35


def test_shutdown(handler: MessageHandler):
    handler.stop_event = SimpleEvent()
    handler.shut_down()
    assert handler.stop_event.is_set() is True


class Test_BaseController:
    @pytest.fixture
    def controller(self) -> BaseController:
        return BaseController(name="controller", context=FakeContext())  # type: ignore

    def test_set_properties(self, controller: BaseController):
        controller.set_parameters(parameters={"some": 5})
        assert controller.some == 5  # type: ignore

    def test_get_properties(self, controller: BaseController):
        controller.whatever = 7  # type: ignore
        assert controller.get_parameters(parameters=["whatever"])["whatever"] == 7

    def test_call(self, controller: BaseController):
        controller.stop_event = SimpleEvent()
        controller.call_action(action="shut_down")
        assert controller.stop_event.is_set() is True
