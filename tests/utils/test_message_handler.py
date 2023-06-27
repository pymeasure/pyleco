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
from pyleco.test import FakeContext

from pyleco.utils.message_handler import MessageHandler, InfiniteEvent, BaseController


@pytest.fixture()
def handler() -> MessageHandler:
    handler = MessageHandler(name="handler", context=FakeContext())
    handler.node = "N1"
    handler.full_name = "N1.handler"
    handler.stop_event = InfiniteEvent()
    return handler


# test communication
def test_send(handler: MessageHandler):
    handler.send("N2.CB", conversation_id=b"rec", message_id=b"sen", data=[["TEST"]])
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"N1.handler", b"rec;sen", b'[["TEST"]]']]


def test_heartbeat(handler: MessageHandler):
    handler.heartbeat()
    assert handler.socket._s == [[VERSION_B, b"COORDINATOR", b"N1.handler", b";"]]


def test_handle_message_ignores_heartbeats(handler: MessageHandler):
    handler.handle_commands = MagicMock()
    # empty message of heartbeat
    handler.socket._r = [[VERSION_B, b"N1.handler", b"whatever", b";"]]
    handler.handle_message()
    handler.handle_commands.assert_not_called()


@pytest.mark.parametrize("i, out", (
    ([VERSION_B, b"N1.handler", b"N1.CB", b"5;6",
      b'{"id": 5, "method": "shutdown", "jsonrpc": "2.0"}'],
     [VERSION_B, b"N1.CB", b"N1.handler", b"5;",
      b'{"id": 5, "result": null, "jsonrpc": "2.0"}']),
))
def test_handle_message(handler: MessageHandler, i, out):
    handler.socket._r = [i]
    handler.handle_message()
    for j in range(len(out)):
        if j == 3:
            continue  # reply adds timestamp
        assert handler.socket._s[0][j] == out[j]


def test_handle_SIGNIN_message_response(handler: MessageHandler):
    handler.socket._r = [Message(receiver=b"N3.handler", sender=b"N3.COORDINATOR", data={
        "id": 0, "result": None, "jsonrpc": "2.0",
    }).get_frames_list()]
    handler.node = None
    handler.handle_message()
    assert handler.node == "N3"


def test_handle_ACK_does_not_change_Namespace(handler: MessageHandler):
    """Test that an ACK does not change the Namespace, if it is already set."""
    handler.socket._r = [[VERSION_B, b"N3.handler", b"N3.COORDINATOR", b";",
                          b'{"id": 3, "result": null, "jsonrpc": "2.0"}']]
    handler.node = "N1"
    handler.handle_message()
    assert handler.node == "N1"


class Test_listen:
    @pytest.fixture
    def handler_l(self, handler):
        event = InfiniteEvent()
        event.set()
        handler.socket._r = [Message(
            "handler", "COORDINATOR",
            data={"id": 2, "result": None, "jsonrpc": "2.0"}).get_frames_list()]
        handler.listen(stop_event=event)
        return handler

    def test_sign_in_and_out_messages(self, handler_l: MessageHandler):
        assert handler_l.socket._s == [
            Message("COORDINATOR", "N1.handler",
                    data={"id": 1, "method": "sign_in", "jsonrpc": "2.0"}).get_frames_list(),
            Message("COORDINATOR", "N1.handler",
                    data={"id": 2, "method": "sign_out", "jsonrpc": "2.0"}).get_frames_list(),
        ]


def test_set_log_level(handler: MessageHandler):
    handler.set_log_level(35)
    assert handler.root_logger.level == 35


def test_shutdown(handler: MessageHandler):
    handler.stop_event = InfiniteEvent()
    handler.shutdown()
    assert handler.stop_event.is_set() is True


class Test_BaseController:
    @pytest.fixture
    def controller(self)  -> BaseController:
        return BaseController(name="controller", context=FakeContext())

    def test_set_properties(self, controller: BaseController):
        controller.set_properties(properties={"some": 5})
        assert controller.some == 5  # type: ignore

    def test_get_properties(self, controller: BaseController):
        controller.whatever = 7  # type: ignore
        assert controller.get_properties(properties=["whatever"])["whatever"] == 7

    def test_call(self, controller: BaseController):
        controller.stop_event = InfiniteEvent()
        controller.call_method(method="shutdown")
        assert controller.stop_event.is_set() is True
