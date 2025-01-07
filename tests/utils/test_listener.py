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

from pyleco.test import FakeCommunicator
from pyleco.core.message import Message

from pyleco.utils.listener import Listener, CommunicatorPipe


@pytest.fixture
def listener() -> Listener:
    listener = Listener(name="test")  # type: ignore
    listener.communicator = FakeCommunicator(name="N.Pipe")  # type: ignore
    return listener


def test_communicator_name_is_returned(listener: Listener):
    assert listener.name == "N.Pipe"


class Test_communicator_closed_at_stopped_listener():
    @pytest.fixture(scope="class")
    def communicator(self) -> CommunicatorPipe:
        # scope is class as starting the listener takes some time
        listener = Listener(name="test")
        listener.start_listen()
        communicator = listener.communicator
        listener.stop_listen()
        return communicator

    def test_socket_closed(self, communicator: CommunicatorPipe):
        assert communicator.socket.closed is True

    def test_internal_method(self, communicator: CommunicatorPipe):
        """A method which is handled in the handler and not sent from the handler via LECO."""
        with pytest.raises(ConnectionRefusedError):
            communicator.ask_handler("pong")

    def test_sending_messages(self, communicator: CommunicatorPipe):
        with pytest.raises(ConnectionRefusedError):
            communicator.send_message(Message("rec", "send"))

    def test_changing_name(self, communicator: CommunicatorPipe):
        with pytest.raises(ConnectionRefusedError):
            communicator.name = "abc"
