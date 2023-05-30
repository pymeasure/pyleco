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

from pyleco.coordinator import Coordinator
from pyleco.intercom import Communicator
from pyleco.utils import Commands, Message
from pyleco.listener import BaseListener


hostname = gethostname()
testlevel = 30
# pytest.skip("Takes too long.", allow_module_level=True)


def start_coordinator(namespace: str, port: int, coordinators=None, **kwargs):
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators)
        print("stopping!")


@pytest.fixture(scope="module")
def leco():
    """A leco setup."""
    glog = logging.getLogger()
    glog.setLevel(logging.DEBUG)
    glog.addHandler(logging.StreamHandler())
    log = logging.getLogger("test")
    threads = []
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N1", port=60001)))
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N2", port=60002)))
    threads.append(threading.Thread(target=start_coordinator,
                                    kwargs=dict(namespace="N3", port=60003)))
    for thread in threads:
        thread.daemon = True
        thread.start()
    listener = BaseListener(name="Controller", port=60001)
    listener.start_listen()
    sleep(1)
    yield listener
    log.info("Tearing down")
    for thread in threads:
        thread.join(0.5)
    listener.stop_listen()


@pytest.mark.skipif(testlevel < 0, reason="reduce load")
def test_startup(leco):
    response = leco.ask_message(Message(receiver=b"COORDINATOR",
                                        data=[[Commands.GET, ["directory", "nodes"]]],
                                        conversation_id=b"12345"))
    # response.header = b""  # reset header for comparison
    assert response == Message(
        receiver=b"N1.Controller", sender=b"N1.COORDINATOR",
        data=[[Commands.ACKNOWLEDGE, {"directory": ["Controller"],
                                      "nodes": {"N1": f"{hostname}:60001"}}]],
        conversation_id=b"12345"
    )


@pytest.mark.skipif(testlevel < 1, reason="reduce load")
def test_connect_N1_to_N2(leco):
    response = leco.ask_as_message(receiver="COORDINATOR",
                                   data=[[Commands.SET, {"nodes": {"N2": "localhost:60002"}}]],
                                   conversation_id=b"connect_N2")
    assert response == Message(
        b"N1.Controller", b"N1.COORDINATOR", data=[[Commands.ACKNOWLEDGE]],
        conversation_id=b"connect_N2"
    )
    sleep(0.5)  # time for coordinators to talk
    response = leco.ask_as_message(receiver="COORDINATOR",
                                   data=[[Commands.GET, ["nodes"]]],
                                   conversation_id=b"connect_N2-2")
    # response.header = b""  # reset header for comparison
    assert response == Message(
        receiver=b"N1.Controller", sender=b"N1.COORDINATOR",
        data=[[Commands.ACKNOWLEDGE, {
            "nodes": {"N1": f"{hostname}:60001", "N2": "localhost:60002"}}]],
        conversation_id=b"connect_N2-2"
    )


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_1_Coordinator(leco):
    c = Communicator(name="whatever", port=60001)
    c.sign_in()
    assert c.ask("N1.Controller", data=[[Commands.PING]]) == Message(
        b'N1.whatever', b'N1.Controller', data=[]
    )


@pytest.mark.skipif(testlevel < 2, reason="reduce load")
def test_Component_to_Component_via_2_Coordinators(leco):
    c = Communicator(name="whatever", port=60002)
    c.sign_in()
    assert c.ask("N1.Controller", data=[[Commands.PING]]) == Message(
        b'N2.whatever', b'N1.Controller', data=[])


@pytest.mark.skipif(testlevel < 3, reason="reduce load")
def test_connect_N3_to_N2(leco):
    c = Communicator(name="whatever", port=60003)
    c.sign_in()
    c.ask(receiver="COORDINATOR",
          data=[[Commands.SET, {"nodes": {"N2": "localhost:60002"}}]],
          conversation_id=b"connect_N2")

    sleep(0.5)  # time for coordinators to talk
    response = leco.ask_as_message(receiver="COORDINATOR",
                                   data=[[Commands.GET, ["nodes"]]],
                                   conversation_id=b"connect_N2-2")
    # response.header = b""  # reset header for comparison
    assert response == Message(
        receiver=b"N1.Controller", sender=b"N1.COORDINATOR",
        data=[[Commands.ACKNOWLEDGE, {
            "nodes": {"N1": f"{hostname}:60001", "N2": "localhost:60002",
                      "N3": f"{hostname}:60003"}}]],
        conversation_id=b"connect_N2-2"
    )


@pytest.mark.skipif(testlevel < 4, reason="reduce load")
def test_shutdown_N3(leco):
    c = Communicator(name="whatever", port=60003)
    c.sign_in()
    c.ask(receiver="N3.COORDINATOR", data=[[Commands.OFF]])

    sleep(0.5)  # time for coordinators to talk
    response = leco.ask_as_message(receiver="COORDINATOR",
                                   data=[[Commands.GET, ["nodes"]]],
                                   conversation_id=b"connect_N2-2")
    # response.header = b""  # reset header for comparison
    assert response == Message(
        receiver=b"N1.Controller", sender=b"N1.COORDINATOR",
        data=[[Commands.ACKNOWLEDGE, {"nodes": {"N1": f"{hostname}:60001",
                                                "N2": "localhost:60002"}}]],
        conversation_id=b"connect_N2-2"
    )
