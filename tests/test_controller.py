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

import time

import pytest

from pymeasure.adapters import ProtocolAdapter
from pymeasure.instruments import Instrument

from pyleco.utils import VERSION_B, FakeContext
from pyleco.controller import InstrumentController, MessageHandler, InfiniteEvent


@pytest.fixture
def handler():
    handler = MessageHandler(name="test", context=FakeContext())
    handler.node = "N1"
    handler.fname = "N1.test"
    handler.stop_event = InfiniteEvent()
    return handler


class FakeController(InstrumentController):

    def _readout(self, device, publisher):
        print("read", time.perf_counter())
        time.sleep(1)

    def queue_readout(self):
        print("queue", time.perf_counter())
        super().queue_readout()

    def heartbeat(self):
        print("beating")
        super().heartbeat()


class FantasyInstrument(Instrument):

    def __init__(self, adapter, name="stuff", *args, **kwargs):
        super().__init__(ProtocolAdapter(), name, includeSCPI=False)
        self._prop = 5
        self._prop2 = 7

    @property
    def prop(self):
        return self._prop

    @prop.setter
    def prop(self, value):
        self._prop = value

    @property
    def prop2(self):
        return self._prop2

    @prop2.setter
    def prop2(self, value):
        self._prop2 = value

    def silent_method(self, value):
        self._method_value = value

    def returning_method(self, value):
        return value ** 2

    @property
    def long(self):
        time.sleep(0.5)
        return 7


# test communication
def test_send(handler):
    handler.send("N2.CB", conversation_id="rec", message_id="sen", data=[["TEST"]])
    assert handler.socket._s == [[VERSION_B, b"N2.CB", b"N1.test", b"rec;sen", b'[["TEST"]]']]


@pytest.mark.parametrize("i, out", (
    ([VERSION_B, b"N1.test", b"N1.CB", b"5;6", b"[]"], [VERSION_B, b"N1.CB", b"N1.test", b"5;", b'[]']),
))
def test_handle_message(handler, i, out):
    handler.socket._r = [i]
    handler.handle_message()
    for j in range(len(out)):
        if j == 3:
            continue  # reply adds timestamp
        assert handler.socket._s[0][j] == out[j]


def test_handle_SIGNIN_message_response(handler):
    handler.socket._r = [[VERSION_B, b"N3.test", b"N3.COORDINATOR", b";", b'[["A"]]']]
    handler.node = None
    handler.handle_message()
    assert handler.node == "N3"


def test_handle_ACK_does_not_change_Namespace(handler):
    """Test that an ACK does not change the Namespace, if it is already set."""
    handler.socket._r = [[VERSION_B, b"N3.test", b"N3.COORDINATOR", b";", b'[["A"]]']]
    handler.node = "N1"
    with pytest.raises(NotImplementedError):
        handler.handle_message()
    assert handler.node == "N1"


# test general methods


@pytest.fixture(scope="module")
def controller():
    return FakeController("test", FantasyInstrument, auto_connect={'adapter': "abc"}, port=1234, protocol="inproc")


def test_get_properties(controller):
    assert controller.get_properties(['prop']) == {'prop': 5}


def test_set_properties(controller):
    controller.set_properties({'prop2': 10})
    assert controller.device.prop2 == 10


def test_call_silent_method(controller):
    assert controller.call("silent_method", [], {'value': 7}) is None
    assert controller.device._method_value == 7


def test_returning_method(controller):
    assert controller.call('returning_method', [], {'value': 2}) == 4


# test communication
def readout(*args):
    pass
    # print("readout", args)
