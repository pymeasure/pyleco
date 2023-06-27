
import time

import pytest

from pyleco.actors.actor import Actor


class FantasyInstrument:

    def __init__(self, adapter, name="FantasyInstrument", *args, **kwargs):
        self.name = name
        self.adapter = adapter
        super().__init__()
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

    def connect(self, *args):
        pass

    def disconnect(self, *args):
        pass


class FakeActor(Actor):

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
def controller() -> FakeActor:
    return FakeActor("test", FantasyInstrument, auto_connect={'adapter': "abc"}, port=1234,
                          protocol="inproc")


def test_get_properties(controller: FakeActor):
    assert controller.get_properties(['prop']) == {'prop': 5}


def test_set_properties(controller: FakeActor):
    controller.set_properties({'prop2': 10})
    assert controller.device.prop2 == 10


def test_call_silent_method(controller: FakeActor):
    assert controller.call_method("silent_method", value=7) is None
    assert controller.device._method_value == 7


def test_returning_method(controller: FakeActor):
    assert controller.call_method('returning_method', value=2) == 4
