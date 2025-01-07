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

from __future__ import annotations
import logging
import threading
from time import sleep

import pytest

from pyleco.coordinators.coordinator import Coordinator
from pyleco.actors.actor import Actor
from pyleco.directors.director import Director


# Constants
PORT = 60004


def start_coordinator(namespace: str, port: int, coordinators=None, **kwargs):
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators)


class FakeInstrument:
    _prop1 = 5

    def __init__(self):
        pass

    def connect(self):
        pass

    @property
    def constant(self):
        return 7

    @property
    def prop1(self):
        return self._prop1

    @prop1.setter
    def prop1(self, value):
        self._prop1 = value

    def triple(self, factor: float = 1, factor2: float = 1) -> float:
        return factor * factor2 * 3


def start_actor(event: threading.Event):
    actor = Actor("actor", FakeInstrument, port=PORT)

    def binary_method_manually() -> None:
        """Receive binary data and return it. Do all the binary things manually."""
        payload = actor.current_message.payload[1:]
        try:
            actor.additional_response_payload = [payload[0] * 2]
        except IndexError:
            pass

    def binary_method_created(additional_payload: list[bytes]) -> tuple[None, list[bytes]]:
        """Receive binary data and return it. Create binary method by registering it."""
        return None, [additional_payload[0] * 2]

    actor.register_rpc_method(binary_method_manually)
    actor.register_binary_rpc_method(
        binary_method_created, accept_binary_input=True, return_binary_output=True
    )
    actor.connect()
    actor.rpc.method()(actor.device.triple)
    actor.register_device_method(actor.device.triple)
    actor.listen(event)
    actor.disconnect()


@pytest.fixture(scope="module")
def director():
    """A leco setup."""
    glog = logging.getLogger()
    glog.setLevel(logging.DEBUG)
    # glog.addHandler(logging.StreamHandler())
    log = logging.getLogger("test")
    stop_event = threading.Event()
    threads = []
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N1", port=PORT)))
    threads.append(threading.Thread(target=start_actor, kwargs=dict(event=stop_event)))
    for thread in threads:
        thread.daemon = True
        thread.start()
    sleep(1)
    director = Director(actor="actor", port=PORT)
    yield director
    log.info("Tearing down")
    stop_event.set()
    director.shut_down_actor(actor="COORDINATOR")
    for thread in threads:
        thread.join(0.5)


def test_get_property(director: Director):
    assert director.get_parameters("constant") == {"constant": 7}


def test_change_property(director: Director):
    start = director.get_parameters(["prop1"])["prop1"]
    director.set_parameters({"prop1": start + 3})
    assert director.get_parameters(["prop1"])["prop1"] == start + 3


def test_call_action_arg(director: Director):
    assert director.call_action("triple", 5) == 15


def test_call_action_kwarg(director: Director):
    assert director.call_action(action="triple", factor=5) == 15


def test_call_action_arg_and_kwarg(director: Director):
    assert director.call_action("triple", 2, factor2=5) == 30


def test_method_via_rpc(director: Director):
    assert director.ask_rpc(method="triple", factor=5) == 15


def test_method_via_rpc2(director: Director):
    assert director.ask_rpc(method="triple", factor=2, factor2=5) == 30


def test_device_method_via_rpc(director: Director):
    assert director.ask_rpc(method="device.triple", factor=5) == 15


def test_binary_data_transfer(director: Director):
    assert director.ask_rpc(
        method="binary_method_manually",
        additional_payload=[b"123"],
        extract_additional_payload=True,
    ) == (None, [b"123123"])


def test_binary_data_transfer_created(director: Director):
    assert director.ask_rpc(
        method="binary_method_created", additional_payload=[b"123"], extract_additional_payload=True
    ) == (None, [b"123123"])
