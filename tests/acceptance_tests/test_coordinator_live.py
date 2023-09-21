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

import logging
from socket import gethostname
from time import sleep
import threading

import pytest

from pyleco.errors import DUPLICATE_NAME
from pyleco.core.message import Message
from pyleco.utils.listener import Listener
from pyleco.utils.communicator import Communicator

from pyleco.coordinators.coordinator import Coordinator


# Constants
PORT = 60001
PORT2 = PORT + 1
PORT3 = PORT + 2


hostname = gethostname()
testlevel = 30
# pytest.skip("Takes too long.", allow_module_level=True)


def start_coordinator(namespace: str, port: int, coordinators=None, stop_event=None, **kwargs):
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators, stop_event=stop_event)
        print("stopping!")


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
    listener = Listener(name="Controller", port=PORT)
    listener.start_listen()
    sleep(1)
    yield listener
    log.info("Tearing down")
    for thread in threads:
        thread.join(0.5)
    listener.stop_listen()
    for event in stop_events:
        event.set()


@pytest.mark.skipif(testlevel < 0, reason="reduce load")
def test_startup(leco: Listener):
    components = leco.ask_rpc(b"COORDINATOR", "send_local_components")
    assert components == ["Controller"]
    nodes = leco.ask_rpc(b"COORDINATOR", "send_nodes")
    assert nodes == {"N1": f"{hostname}:{PORT}"}


@pytest.mark.skipif(testlevel < 1, reason="reduce load")
def test_connect_N1_to_N2(leco: Listener):
    response = leco.ask_rpc("COORDINATOR", method="add_nodes", nodes={"N2": f"localhost:{PORT2}"})
    assert response is None
    sleep(0.5)  # time for coordinators to talk
    nodes = leco.ask_rpc(receiver="COORDINATOR", method="send_nodes")
    assert nodes == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}"}
    assert leco.ask_rpc(receiver="N2.COORDINATOR", method="pong") is None


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_1_Coordinator(leco: Listener):
    with Communicator(name="whatever", port=PORT) as c:
        assert c.ask_rpc("N1.Controller", method="pong") is None


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_2_Coordinators(leco: Listener):
    with Communicator(name="whatever", port=PORT2) as c:
        response = c.ask("N1.Controller", data={"id": 1, "method": "pong", "jsonrpc": "2.0"})
        assert response == Message(
            b'N2.whatever', b'N1.Controller', data={"id": 1, "result": None, "jsonrpc": "2.0"},
            header=response.header)


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_lists_propgate_through_Coordinators(leco: Listener):
    """Test that Component lists are propagated from one Coordinator to another."""
    with Communicator(name="whatever", port=PORT2) as c:
        response = c.ask("N2.COORDINATOR", data={
            "id": 1, "method": "send_global_components", "jsonrpc": "2.0"})
        assert response == Message(
            b'N2.whatever', b'N2.COORDINATOR', data={
                "id": 1, "result": {"N1": ["Controller"], "N2": ["whatever"]}, "jsonrpc": "2.0"},
            header=response.header)


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_second_coordinator(leco: Listener):
    assert leco.ask_rpc("N2.COORDINATOR", method="pong") is None


def test_sign_in_rejected_for_duplicate_name(leco: Listener):
    with pytest.raises(ConnectionRefusedError, match=DUPLICATE_NAME.message):
        with Communicator(name="Controller", port=PORT):
            pass


@pytest.mark.skipif(testlevel < 3, reason="reduce load")
def test_connect_N3_to_N2(leco: Listener):
    c = Communicator(name="whatever", port=PORT3)
    c.sign_in()
    c.ask_rpc(b"COORDINATOR", "add_nodes", nodes={"N2": f"localhost:{PORT2}"})

    sleep(0.5)  # time for coordinators to talk
    nodes = leco.ask_rpc(receiver="COORDINATOR", method="send_nodes")
    assert nodes == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}",
                     "N3": f"{hostname}:{PORT3}"}


@pytest.mark.skipif(testlevel < 4, reason="reduce load")
def test_shutdown_N3(leco: Listener):
    c = Communicator(name="whatever", port=PORT3)
    c.sign_in()
    c.ask(receiver="N3.COORDINATOR", data={"id": 3, "method": "shut_down", "jsonrpc": "2.0"})

    sleep(0.5)  # time for coordinators to talk
    nodes = leco.ask_rpc(receiver="COORDINATOR", method="send_nodes")
    assert nodes == {"N1": f"{hostname}:{PORT}", "N2": f"localhost:{PORT2}"}
