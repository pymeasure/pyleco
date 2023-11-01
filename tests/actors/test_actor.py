
import time

from unittest.mock import MagicMock

import pytest

from pyleco.test import FakePoller
from pyleco.actors.actor import Actor
from pyleco.core.leco_protocols import PollingActorProtocol, ExtendedComponentProtocol, Protocol


class FantasyChannel:
    def __init__(self) -> None:
        self._prop = -1

    @property
    def channel_property(self):
        return self._prop

    @channel_property.setter
    def channel_property(self, value):
        self._prop = value

    def channel_method(self, value):
        return 2 * value


class FantasyInstrument:

    def __init__(self, adapter, name="FantasyInstrument", *args, **kwargs):
        self.name = name
        self.adapter = adapter
        super().__init__()
        self._prop = 5
        self._prop2 = 7
        self.channel = FantasyChannel()
        self.channel.trace = FantasyChannel()  # type: ignore

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

    def queue_readout(self):
        print("queue", time.perf_counter())
        super().queue_readout()

    def heartbeat(self):
        print("beating")
        super().heartbeat()


class ExtendedActorProtocol(ExtendedComponentProtocol, PollingActorProtocol, Protocol):
    pass


@pytest.fixture()
def actor() -> FakeActor:
    actor = FakeActor("test", FantasyInstrument, auto_connect={'adapter': MagicMock()}, port=1234,
                      protocol="inproc")
    actor.next_beat = float("inf")
    return actor


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(ExtendedActorProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: ExtendedActorProtocol):
            pass
        testing(FakeActor(name="test", cls=FantasyInstrument))

    @pytest.fixture
    def component_methods(self, actor: Actor):
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


def test_get_properties(actor: Actor):
    assert actor.get_parameters(['prop']) == {'prop': 5}


def test_get_channel_properties(actor: Actor):
    assert actor.get_parameters(["channel.channel_property"]) == {
        "channel.channel_property": -1}


def test_get_nested_channel_properties(actor: Actor):
    assert actor.get_parameters(["channel.trace.channel_property"]) == {
        "channel.trace.channel_property": -1}


def test_set_properties(actor: Actor):
    actor.set_parameters({'prop2': 10})
    assert actor.device.prop2 == 10


def test_set_channel_properties(actor: Actor):
    actor.set_parameters(parameters={'channel.channel_property': 10})
    assert actor.device.channel.channel_property == 10


def test_set_nested_channel_properties(actor: Actor):
    actor.set_parameters(parameters={'channel.trace.channel_property': 10})
    assert actor.device.channel.trace.channel_property == 10  # type: ignore


def test_call_silent_method(actor: Actor):
    assert actor.call_action("silent_method", kwargs=dict(value=7)) is None
    assert actor.device._method_value == 7


def test_returning_method(actor: Actor):
    assert actor.call_action('returning_method', kwargs=dict(value=2)) == 4


def test_channel_method(actor: Actor):
    assert actor.call_action("channel.channel_method", args=(7,)) == 14


def test_nested_channel_method(actor: Actor):
    assert actor.call_action("channel.trace.channel_method", args=(7,)) == 14


def test_register_device_method(actor: Actor):
    actor.register_device_method(actor.device.returning_method)
    response = actor.rpc.process_request(
            '{"id": 1, "method": "device.returning_method", "params": [5], "jsonrpc": "2.0"}')
    result = actor.rpc_generator.get_result_from_response(response)  # type: ignore
    assert result == 25


class Test_disconnect:
    @pytest.fixture
    def disconnected_actor(self):
        actor = FakeActor("name", cls=FantasyInstrument, auto_connect={"adapter": MagicMock()})
        actor._device = actor.device  # type: ignore
        actor.device.adapter.close = MagicMock()
        actor.disconnect()
        return actor

    def test_device_deleted(self, disconnected_actor: Actor):
        assert not hasattr(disconnected_actor, "device")

    def test_timer_canceled(self, disconnected_actor: Actor):
        assert disconnected_actor.timer.finished.is_set() is True

    def test_device_closed(self, disconnected_actor: Actor):
        disconnected_actor._device.adapter.close.assert_called_once()  # type: ignore


def test_exit_calls_disconnect():
    with FakeActor("name", cls=FantasyInstrument) as actor:
        actor.disconnect = MagicMock()
    actor.disconnect.assert_called_once()


class Test_listen_loop_element:
    @pytest.fixture
    def looped_actor(self, actor: Actor):
        """Check a loop with a value in the pipe"""
        poller = FakePoller()
        poller.register(actor.pipeL)
        actor.queue_readout()  # enqueue a readout
        actor.readout = MagicMock()  # type: ignore
        # act
        socks = actor._listen_loop_element(poller=poller,  # type: ignore
                                           waiting_time=None)
        actor._socks = socks  # type: ignore  # for assertions
        return actor

    def test_socks_empty(self, looped_actor: Actor):
        assert looped_actor._socks == {}  # type: ignore

    def test_readout_called(self, looped_actor: Actor):
        looped_actor.readout.assert_called_once()  # type: ignore

    def test_no_readout_queued(self, actor: Actor):

        poller = FakePoller()
        poller.register(actor.pipeL)
        actor.readout = MagicMock()  # type: ignore
        # act
        actor._listen_loop_element(poller=poller,  # type: ignore
                                   waiting_time=0)
        actor.readout.assert_not_called()


def test_timer_enqueues_heartbeat(actor: Actor):
    actor.start_timer(0.0000001)  # s
    assert actor.pipeL.poll(timeout=50) == 1  # ms


def test_restart_stopped_timer(actor: Actor):
    """Starting a stopped timer is impossible, ensure, that it works as expected (new timer)."""
    actor.start_timer(10)  # s
    actor.stop_timer()
    actor.start_timer(0.0000001)  # s
    assert actor.pipeL.poll(timeout=50) == 1  # ms
