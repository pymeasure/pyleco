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
from socket import gethostname
from time import sleep
import threading

import pytest

from pyleco.core.message import Message, MessageTypes
from pyleco.utils.listener import Listener
from pyleco.utils.communicator import Communicator

# Test the Coordinator and its Director in a live test
from pyleco.directors.coordinator_director import CoordinatorDirector
from pyleco.coordinators.coordinator import Coordinator


# Constants
PORT = 60001
PORT2 = PORT + 1
PORT3 = PORT + 2
TALKING_TIME = 0.5  # s
TIMEOUT = 2  # s


hostname = gethostname()
testlevel = 30
# pytest.skip("Takes too long.", allow_module_level=True)


def start_coordinator(namespace: str, port: int, coordinators=None, stop_event=None, **kwargs):
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators, stop_event=stop_event)


@pytest.fixture(scope="module")
def leco():
    """A leco setup."""
    glog = logging.getLogger()
    glog.setLevel(logging.DEBUG)
    # glog.addHandler(logging.StreamHandler())
    log = logging.getLogger("test")
    threads = []
    stop_events = [threading.Event(), threading.Event(), threading.Event()]
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N1", port=PORT,
                                                stop_event=stop_events[0])))
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N2", port=PORT2,
                                                stop_event=stop_events[1])))
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N3", port=PORT3,
                                                stop_event=stop_events[2])))
    for thread in threads:
        thread.daemon = True
        thread.start()
    listener = Listener(name="Controller", port=PORT, timeout=TIMEOUT)
    listener.start_listen()
    sleep(TALKING_TIME)  # time for setup
    yield listener.get_communicator()
    log.info("Tearing down")
    listener.stop_listen()
    for event in stop_events:
        event.set()
    for thread in threads:
        thread.join(0.5)


@pytest.mark.skipif(testlevel < 0, reason="reduce load")
def test_startup(leco: Communicator):
    with CoordinatorDirector(communicator=leco) as d:
        assert d.get_local_components() == ["Controller"]
        assert d.get_nodes() == {"N1": f"{hostname}:{PORT}"}


@pytest.mark.skipif(testlevel < 1, reason="reduce load")
def test_connect_N1_to_N2(leco: Communicator):
    with CoordinatorDirector(communicator=leco) as d:
        d.add_nodes({"N2": f"localhost:{PORT2}"})
        sleep(TALKING_TIME)  # time for coordinators to talk
        # assert that the N1.COORDINATOR knows about N2
        assert d.get_nodes() == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}"}
        # assert that the listener can contact N2.COORDINATOR
        assert d.ask_rpc(actor="N2.COORDINATOR", method="pong") is None


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_1_Coordinator(leco: Communicator):
    with Communicator(name="whatever", port=PORT) as c:
        assert c.ask_rpc("N1.Controller", method="pong") is None


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_2_Coordinators(leco: Communicator):
    with Communicator(name="whatever", port=PORT2) as c:
        response = c.ask("N1.Controller", data={"id": 1, "method": "pong", "jsonrpc": "2.0"},
                         message_type=MessageTypes.JSON)
        assert response == Message(
            b'N2.whatever', b'N1.Controller', data={"id": 1, "result": None, "jsonrpc": "2.0"},
            header=response.header)


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_lists_propgate_through_Coordinators(leco: Communicator):
    """Test that Component lists are propagated from one Coordinator to another."""
    with CoordinatorDirector(actor="N2.COORDINATOR", name="whatever", port=PORT2) as d:
        assert d.get_global_components() == {"N1": ["Controller"], "N2": ["whatever"]}


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_second_coordinator(leco: Communicator):
    assert leco.ask_rpc("N2.COORDINATOR", method="pong") is None


def test_sign_in_rejected_for_duplicate_name(leco: Communicator):
    with pytest.raises(ConnectionRefusedError):
        with Communicator(name="Controller", port=PORT):
            pass


@pytest.mark.skipif(testlevel < 3, reason="reduce load")
def test_connect_N3_to_N2(leco: Communicator):
    with CoordinatorDirector(name="whatever", port=PORT3) as d1:
        d1.add_nodes({"N2": f"localhost:{PORT2}"})

    sleep(TALKING_TIME)  # time for coordinators to talk
    with CoordinatorDirector(actor="COORDINATOR", communicator=leco) as d2:
        assert d2.get_nodes() == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}",
                                  "N3": f"{hostname}:{PORT3}"}


@pytest.mark.skipif(testlevel < 4, reason="reduce load")
def test_shutdown_N3(leco: Communicator):
    with CoordinatorDirector(actor="N3.COORDINATOR", name="whatever", port=PORT3) as d1:
        d1.shut_down_actor()

    sleep(TALKING_TIME)  # time for coordinators to talk
    with CoordinatorDirector(actor="COORDINATOR", communicator=leco) as d2:
        assert d2.get_nodes() == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}"}
