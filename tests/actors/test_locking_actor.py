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

import logging
import time

from unittest.mock import MagicMock

import pytest

from pyleco.core.message import Message
from pyleco.actors.locking_actor import LockingActor, AccessDeniedError
from pyleco.core.leco_protocols import LockingActorProtocol


class FantasyChannel:
    def __init__(self) -> None:
        self._prop = -1

    @property
    def channel_property(self):
        return self._prop

    @channel_property.setter
    def channel_property(self, value):
        self._prop = value

    @property
    def l_c_prop(self):
        return self._prop

    @l_c_prop.setter
    def l_c_prop(self, value):
        self._prop = value

    def channel_method(self, value):
        return 2 * value


class FantasyInstrument:
    """Some instrument to be controlled.

    The prefix "l" indicates properties etc. which should be locked.
    """
    def __init__(self, adapter, name="FantasyInstrument", *args, **kwargs):
        self.name = name
        self.adapter = adapter
        super().__init__()
        self.l_channel = FantasyChannel()
        self.l_channel.trace = FantasyChannel()  # type: ignore
        self.o_channel = FantasyChannel()
        self._l_prop = 5
        self._o_prop = 6

    @property
    def l_prop(self):
        return self._l_prop

    @l_prop.setter
    def l_prop(self, value):
        self._l_prop = value

    @property
    def o_prop(self):
        return self._o_prop

    @o_prop.setter
    def o_prop(self, value):
        self._o_prop = value

    def l_method(self, value):
        self._method_value = value

    def o_method(self, value):
        return value**2

    # methods for Instrument simulation
    def connect(self, *args):
        pass

    def disconnect(self, *args):
        pass


class FakeActor(LockingActor):
    def queue_readout(self):
        logging.getLogger().info(f"queue: {time.perf_counter()}")
        super().queue_readout()

    def heartbeat(self):
        logging.getLogger().info("beating")
        super().heartbeat()


@pytest.fixture()
def actor() -> FakeActor:
    actor = FakeActor(
        "test",
        FantasyInstrument,
        auto_connect={"adapter": MagicMock()},
        port=1234,
        protocol="inproc",
    )
    actor.next_beat = float("inf")
    return actor


resources = (
    "l_prop",  # a property
    "l_method",  # a method
    "l_channel",  # a channel
    "l_channel.l_c_prop",  # property of a channel
    "o_channel.l_c_prop",  # property of a channel
)


@pytest.fixture
def locked_actor(actor: LockingActor) -> LockingActor:
    actor.current_message = Message("rec", "owner")
    for r in resources:
        actor.lock(r)
    actor.current_message = Message("rec", "requester")
    return actor


class TestProtocolImplemented:
    protocol_methods = [m for m in dir(LockingActorProtocol) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: LockingActorProtocol):
            pass

        testing(FakeActor(name="test", device_class=FantasyInstrument))

    @pytest.fixture
    def component_methods(self, actor: LockingActor):
        response = actor.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}'
        )
        result = actor.rpc_generator.get_result_from_response(response)  # type: ignore
        return result.get("methods")

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(self, component_methods, method):
        for m in component_methods:
            if m.get("name") == method:
                return
        raise AssertionError(f"Method {method} is not available.")

class Test_check_access_rights:
    @pytest.mark.parametrize("resource", resources)
    def test_owner(self, locked_actor: LockingActor, resource):
        locked_actor.current_message = Message("rec", "owner")
        assert locked_actor.check_access_rights(resource) is True

    @pytest.mark.parametrize("resource", ("l_channel.channel_property", "l_channel.trace"))
    def test_owner_of_parent(self, locked_actor: LockingActor, resource):
        locked_actor.current_message = Message("rec", "owner")
        assert locked_actor.check_access_rights(resource) is True

    @pytest.mark.parametrize("resource", (None, *resources))
    def test_owner_of_device(self, actor: LockingActor, resource):
        """Only the device itself is locked, test access to parts."""
        actor.current_message = Message("rec", "owner")
        actor.lock(None)
        # act and assert
        assert actor.check_access_rights(resource) is True

    @pytest.mark.parametrize(
        "resource", (None, "o_prop", "o_method", "o_channel", "o_channel.channel_property")
    )
    def test_requester_True(self, locked_actor: LockingActor, resource):
        """Test that another requester may access unlocked resources."""
        locked_actor.current_message = Message("rec", "requester")
        assert locked_actor.check_access_rights(resource) is True

    @pytest.mark.parametrize(
        "resource", ("l_channel", "l_channel.channel_property", "l_prop", "o_channel.l_c_prop")
    )
    def test_requester_False(self, locked_actor: LockingActor, resource):
        # arrange
        locked_actor.force_unlock(None)
        # act
        locked_actor.current_message = Message("rec", "requester")
        assert locked_actor.check_access_rights(resource) is False

    @pytest.mark.parametrize("resource", (None, *resources))
    def test_not_owner_of_device(self, actor: LockingActor, resource):
        """Only the device itself is locked, test access to parts of it."""
        actor.current_message = Message("rec", "owner")
        actor.lock(None)
        actor.current_message = Message("rec", "requester")
        # act and assert
        assert actor.check_access_rights(resource) is True


@pytest.mark.parametrize(
    "resource",
    resources,
)
def test_lock_unlocked(actor: LockingActor, resource):
    actor.current_message = Message("rec", "owner")
    assert actor.lock(resource) is True
    assert actor._locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    resources,
)
def test_lock_already_locked(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "owner")
    assert locked_actor.lock(resource) is True
    assert locked_actor._locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    resources,
)
def test_lock_fail_as_already_locked(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor.lock(resource) is False
    assert locked_actor._locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    resources,
)
def test_unlock_locked(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "owner")
    locked_actor.unlock(resource)
    assert resource not in locked_actor._locks


@pytest.mark.parametrize("resource", (None, "prop"))
def test_unlock_already_unlocked(actor: LockingActor, resource):
    actor.current_message = Message("rec", "requester")
    actor.unlock(resource)
    # assert no error is raised


@pytest.mark.parametrize(
    "resource",
    resources,
)
def test_unlock_fail_as_different_user(locked_actor: LockingActor, resource):
    locked_actor.current_message = Message("rec", "requester")
    # with pytest.raises(AccessDeniedError, match=resource):
    locked_actor.unlock(resource)
    assert locked_actor._locks[resource] == b"owner"


@pytest.mark.parametrize(
    "resource",
    ("l_channel.channel_method", "l_channel.trace"),
)
def test_lock_fail_for_child_of_locked_resource(locked_actor: LockingActor, resource):
    """If the parent is locked (e.g. the device), no child may be locked."""
    locked_actor.current_message = Message("rec", "requester")
    assert locked_actor.lock(resource) is False


# test device access
def test_get_parameters_successfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "owner")
    locked_actor.get_parameters(["l_prop", "l_channel.channel_property", "o_prop"])
    # assert that no error is raised


def test_get_parameters_unsuccessfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "requester")
    with pytest.raises(AccessDeniedError, match="'l_prop'"):
        locked_actor.get_parameters(["o_prop", "l_prop"])


def test_set_parameters_successfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "owner")
    locked_actor.set_parameters({"l_prop": 5, "l_channel.channel_property": 6})
    # assert that no error is raised


def test_set_parameters_unsuccessfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "requester")
    with pytest.raises(AccessDeniedError, match="'l_prop'"):
        locked_actor.set_parameters({"o_prop": 5, "l_prop": 6})


def test_call_action_successfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "owner")
    locked_actor.call_action("l_method", [5])
    # assert that no error is raised


def test_call_action_unsuccessfully(locked_actor: LockingActor):
    locked_actor.current_message = Message("rec", "requester")
    with pytest.raises(AccessDeniedError, match="'l_method'"):
        locked_actor.call_action("l_method", [5])
