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

import pytest

from pyleco.utils import VERSION_B, FakeSocket, FakeContext
from pyleco.coordinator import Coordinator


@pytest.fixture
def coordinator():
    coordinator = Coordinator(node="N1", host="N1host", cleaning_interval=1e5, context=FakeContext())
    coordinator.directory = {b"send": b"321", b"rec": b"123"}
    coordinator.dealers[b"N2"] = FakeSocket("zmq.DEALER")
    coordinator.node_identities[b"n2"] = b"N2"
    coordinator.node_addresses[b"N2"] = "N2host", 12300
    return coordinator


def fake_perf_counter():
    return 0


@pytest.fixture()
def fake_counting(monkeypatch):
    monkeypatch.setattr("coordinator.perf_counter", fake_perf_counter)


# TODO cleaning anpassen an neue Begebenheiten
# @pytest.fixture()
# def cleaning(fake_counting, coordinator):
#     coordinator.heartbeats = {-2: -2, -1: -1.1, -0.5: -0.5, -0.1: -0.1}
#     coordinator.addresses = {-2: 1, -1: 1, -0.5: 1, -0.1: 1}
#     coordinator.clean_addresses(expiration_time=1)
#     return coordinator


# def test_clean_addresses(cleaning):
#     assert cleaning.addresses == {-0.5: 1, -0.1: 1}


# def test_clean_heartbeats(cleaning):
#     assert cleaning.heartbeats == {-0.5: -0.5, -0.1: -0.1}


def test_heartbeat_local(coordinator, fake_counting):
    coordinator.sock._r = [[b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""]]
    coordinator._routing()
    assert coordinator.heartbeats[b"send"] == 0


@pytest.mark.parametrize("i, o", (
    ([b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""], None),  # test heartbeat alone
    ([b"321", VERSION_B, b"rec", b"send", b";", b"1"], [b"123", VERSION_B, b"rec", b"send", b";", b"1"]),  # receiver known, sender given.
    ([b"321", VERSION_B, b"x", b"send", b";", b""], [b"321", VERSION_B, b"send", b"N1.COORDINATOR", b";", b'[["E", "Receiver \'b\'x\'\' is not in addresses list."]]']),  # receiver unknown, return to sender
    ([b"321", VERSION_B, b"N3.CB", b"N1.send", b";"], [b"321", VERSION_B, b"N1.send", b"N1.COORDINATOR", b";", b'[["E", "Node b\'N3\' is not known."]]']),
))
def test_routing(coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`."""
    coordinator.sock._r = [i]
    coordinator._routing()
    if o is None:
        assert coordinator.sock._s == []
    else:
        assert coordinator.sock._s == [o]


def test_remote_routing(coordinator):
    coordinator.sock._r = [[b"321", VERSION_B, b"N2.CB", b"N1.send", b";"]]
    coordinator._routing()
    assert coordinator.dealers[b"N2"]._s == [[VERSION_B, b"N2.CB", b"N1.send", b";"]]


def test_remote_heartbeat(coordinator, fake_counting):
    coordinator.sock._r = [[b"1", VERSION_B, b"N2.CB", b"N3.CA", b";"]]
    coordinator._routing()
    assert coordinator.node_heartbeats[b"1"] == 0


# Test Coordinator commands handling
# TODO test individual Coordinator commands and their execution.
def test_signin(coordinator):
    coordinator.sock._r = [[b'cb', VERSION_B, b"COORDINATOR", b"CB", b";", b'[["SI"]]']]
    coordinator._routing()
    assert coordinator.sock._s == [[b"cb", VERSION_B, b"CB", b"N1.COORDINATOR", b";", b'[["SI", "N1"]]']]


def test_signout_clears_address(coordinator):
    coordinator.sock._r = [[b'123', VERSION_B, b"N1.COORDINATOR", b"rec", b";", b'[["D"]]']]
    coordinator._routing()
    assert b"rec" not in coordinator.directory.keys()
    assert coordinator.sock._s == [[b"123", VERSION_B, b"rec", b"N1.COORDINATOR", b";", b'[["A"]]']]


def test_co_signin_successful(coordinator):
    coordinator.sock._r = [[b'n3', VERSION_B, b"COORDINATOR", b"N3.COORDINATOR", b";", b'[["COS"]]']]
    coordinator._routing()
    assert b'n3' in coordinator.node_identities.keys()
    assert coordinator.sock._s[0] == [b'n3', VERSION_B, b"N3.COORDINATOR", b"N1.COORDINATOR", b";", b'[["A"]]']


def test_set_directory(coordinator):
    coordinator.sock._r = [[b"n2", VERSION_B, b"N1.COORDINATOR",
                            b"N2.COORDINATOR", b";", b'[["S", {"directory": ["send", "rec"], "nodes": {"N1": ["N1host", 12300], "N2": ["wrong_host", -7], "N3": ["N3host", 12300]}}]]']]
    coordinator._routing()
    assert coordinator.global_directory == {b"N2": ["send", "rec"]}
    assert b"N1" not in coordinator.dealers.keys()  # not created
    assert coordinator.node_addresses[b"N2"] == ("N2host", 12300)  # not changed
    assert b"N3" in coordinator.dealers.keys()  # newly created


class Test_add_coordinator:
    @pytest.fixture
    def coordinator_added(self, coordinator):
        coordinator.add_coordinator("host", node=12345)
        return coordinator

    def test_socket_created(self, coordinator_added):
        assert coordinator_added.dealers[12345].addr == "tcp://host:12300"

    def test_COS_message_sent(self, coordinator_added):
        assert coordinator_added.dealers[12345]._s == [
            [VERSION_B, b"COORDINATOR", b"N1.COORDINATOR", b";", b'[["COS", {"host": "N1host", "port": 12300}]]']]

    def test_address_added(self, coordinator_added):
        assert coordinator_added.node_addresses[12345] == ("host", 12300)

    def test_waiting_dealer(self, coordinator_added):
        assert 12345 in coordinator_added.waiting_dealers.keys()


class Test_handle_dealer_message:
    @pytest.fixture
    def c_message_handled(self, coordinator):
        coordinator.add_coordinator("N3host", node=12345)
        sock = coordinator.dealers[12345]
        sock._s = []  # reset effects of add_coordinator
        sock._r = [[VERSION_B, b"N1.COORDINATOR", b"N3.COORDINATOR", b";", b'[["A"]]']]
        coordinator.handle_dealer_message(sock, 12345)
        return coordinator

    def test_name_changed(self, c_message_handled):
        assert b"N3" in c_message_handled.dealers.keys()
        assert 12345 not in c_message_handled.dealers.keys()

    def test_socket_not_waiting_anymore(self, c_message_handled):
        assert 12345 not in c_message_handled.waiting_dealers.keys()

    def test_address_name_changed(self, c_message_handled):
        assert 12345 not in c_message_handled.node_addresses.keys()
        assert c_message_handled.node_addresses[b"N3"] == ("N3host", 12300)

    def test_directory_sent(self, c_message_handled):
        assert c_message_handled.dealers[b"N3"]._s == [
            [VERSION_B, b"N3.COORDINATOR", b"N1.COORDINATOR", b";",
             b'[["S", {"directory": ["send", "rec"], "nodes": {"N1": ["N1host", 12300], "N2": ["N2host", 12300], "N3": ["N3host", 12300]}}]]']]
