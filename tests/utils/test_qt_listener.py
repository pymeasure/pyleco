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

from pyleco.test import FakeCommunicator, FakeContext
from pyleco.core.message import Message, MessageTypes

try:
    from pyleco.utils.qt_listener import QtListener, QtPipeHandler, ListenerSignals
except ModuleNotFoundError:
    pytest.skip(reason="qtpy not installed.", allow_module_level=True)

cid = b"conversation_id;"


@pytest.fixture
def signal():
    class FakeSignal:
        def emit(self, message: Message):
            self._content = message
    return FakeSignal()


@pytest.fixture
def qt_listener(signal) -> QtListener:
    qt_listener = QtListener(name="test")  # type: ignore
    qt_listener.communicator = FakeCommunicator(name="N.Pipe")  # type: ignore
    qt_listener.signals.message = signal
    return qt_listener


@pytest.fixture
def qt_handler(signal) -> QtPipeHandler:
    handler = QtPipeHandler(name="handler",
                            context=FakeContext(),  # type: ignore
                            signals=ListenerSignals())
    handler.signals.message = signal
    return handler


class Test_handle_message:
    def test_handle_valid_jsonrpc(self, qt_handler: QtPipeHandler):
        msg = Message("N.Pipe", "sender",
                      data={"jsonrpc": "2.0", "method": "abc", "id": 6},
                      message_type=MessageTypes.JSON,
                      conversation_id=cid,
                      )
        qt_handler.handle_message(msg)
        assert qt_handler.signals.message._content == msg  # type: ignore

    def test_empty_message(self, qt_handler: QtPipeHandler):
        msg = Message("N.Pipe", "sender")
        qt_handler.handle_message(msg)
        assert qt_handler.signals.message._content == msg  # type: ignore

    def test_local_method(self, qt_handler: QtPipeHandler):
        msg = Message("handler", "sender",
                      conversation_id=cid, message_type=MessageTypes.JSON,
                      data={"jsonrpc": "2.0", "method": "pong", "id": 3})
        qt_handler.handle_message(msg)
        assert Message.from_frames(*qt_handler.socket._s[0]) == Message(  # type: ignore
            "sender", "handler", conversation_id=cid, message_type=MessageTypes.JSON,
            data={"jsonrpc": "2.0", "result": None, "id": 3}
        )

