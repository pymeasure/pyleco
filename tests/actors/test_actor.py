
import time

import pytest

from pyleco.actors.actor import Actor
from pyleco.core.leco_protocols import PollingActorProtocol, ExtendedComponentProtocol, Protocol


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


class ExtendedActorProtocol(ExtendedComponentProtocol, PollingActorProtocol, Protocol):
    pass


@pytest.fixture(scope="module")
def actor() -> FakeActor:
    return FakeActor("test", FantasyInstrument, auto_connect={'adapter': "abc"}, port=1234,
                     protocol="inproc")


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(ExtendedActorProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: ExtendedActorProtocol):
            pass
        testing(FakeActor(name="test", cls=FantasyInstrument))

    @pytest.fixture
    def component_methods(self, actor: FakeActor):
        response = actor.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}')
        result = actor.rpc_generator.get_result_from_response(response)  # type: ignore
        return result.get('methods')

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(self, component_methods, method):
        for m in component_methods:
            if m.get('name') == method:
                return
        raise AssertionError(f"Method {method} is not available.")


def test_get_properties(actor: FakeActor):
    assert actor.get_parameters(['prop']) == {'prop': 5}


def test_set_properties(actor: FakeActor):
    actor.set_parameters({'prop2': 10})
    assert actor.device.prop2 == 10


def test_call_silent_method(actor: FakeActor):
    assert actor.call_action("silent_method", kwargs=dict(value=7)) is None
    assert actor.device._method_value == 7


def test_returning_method(actor: FakeActor):
    assert actor.call_action('returning_method', kwargs=dict(value=2)) == 4
