
import time

from pymeasure.adapters import ProtocolAdapter
from pymeasure.instruments import Instrument
import pytest

from pyleco.actors.actor import Actor


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


class FakeController(Actor):

    def _readout(self, device, publisher):
        print("read", time.perf_counter())
        time.sleep(1)

    def queue_readout(self):
        print("queue", time.perf_counter())
        super().queue_readout()

    def heartbeat(self):
        print("beating")
        super().heartbeat()


@pytest.fixture(scope="module")
def controller():
    return FakeController("test", FantasyInstrument, auto_connect={'adapter': "abc"}, port=1234,
                          protocol="inproc")


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
