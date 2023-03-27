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

from pyleco.utils import VERSION_B, FakeSocket, FakeContext, Commands, Errors
from pyleco.coordinator import Coordinator


@pytest.fixture
def coordinator():
    coordinator = Coordinator(node="N1", host="N1host", cleaning_interval=1e5, context=FakeContext())
    coordinator.directory = {b"send": b"321", b"rec": b"123"}
    coordinator.add_coordinator("N2host", node=b"N2")
    coordinator.dealers[b"N2"]._s = []  # reset dealer socket.
    coordinator.node_identities[b"n2"] = b"N2"
    coordinator.node_heartbeats[b"n2"] = -1
    return coordinator


def fake_perf_counter():
    return 0.


@pytest.fixture()
def fake_counting(monkeypatch):
    monkeypatch.setattr("pyleco.coordinator.perf_counter", fake_perf_counter)


class Test_clean_addresses:
    # TODO add tests

    def test_expired_component(self, coordinator, fake_counting):
        coordinator.heartbeats[b"send"] = -3.5
        coordinator.clean_addresses(1)
        assert b"send" not in coordinator.heartbeats
        assert b"send" not in coordinator.directory

    def test_warn_component(self, coordinator, fake_counting):
        coordinator.heartbeats[b"send"] = -1.5
        coordinator.clean_addresses(1)
        assert coordinator.sock._s == [[b"321", VERSION_B, b"N1.send", b"N1.COORDINATOR", b";", b'[["P"]]']]

    def test_active_Component(self, coordinator, fake_counting):
        coordinator.heartbeats[b"send"] = -0.5
        coordinator.clean_addresses(1)
        assert coordinator.sock._s == []
        assert b"send" in coordinator.directory

    def test_expired_Coordinator(self, coordinator, fake_counting):
        coordinator.node_heartbeats[b"n2"] = -3.5
        coordinator.clean_addresses(1)
        assert b"n2" not in coordinator.node_heartbeats
        # further removal tests in :class:`Test_remove_coordinator`

    def test_warn_Coordinator(self, coordinator, fake_counting):
        coordinator.node_heartbeats[b"n2"] = -1.5
        coordinator.clean_addresses(1)
        assert coordinator.dealers[b"N2"]._s == [[VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b";", b'[["P"]]']]

    def test_active_Coordinator(self, coordinator, fake_counting):
        coordinator.node_heartbeats[b"n2"] = -0.5
        coordinator.clean_addresses(1)
        assert b"n2" in coordinator.node_heartbeats


def test_heartbeat_local(coordinator, fake_counting):
    coordinator.sock._r = [[b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""]]
    coordinator._routing()
    assert coordinator.heartbeats[b"send"] == 0


@pytest.mark.parametrize("i, o", (
    ([b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""], None),  # test heartbeat alone
    ([b"321", VERSION_B, b"rec", b"send", b";", b"1"], [b"123", VERSION_B, b"rec", b"send", b";", b"1"]),  # receiver known, sender known.
))
def test_routing_successful(coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: successful routing."""
    coordinator.sock._r = [i]
    coordinator._routing()
    if o is None:
        assert coordinator.sock._s == []
    else:
        assert coordinator.sock._s == [o]


@pytest.mark.parametrize("i, o", (
    # receiver unknown, return to sender:
    ([b"321", VERSION_B, b"x", b"send", b";", b""], [b"321", VERSION_B, b"send", b"N1.COORDINATOR", b";", b'[["E", "Receiver is not in addresses list.", "x"]]']),
    # unknown receiver node:
    ([b"321", VERSION_B, b"N3.CB", b"N1.send", b";"], [b"321", VERSION_B, b"N1.send", b"N1.COORDINATOR", b";", b'[["E", "Node is not known.", "N3"]]']),
    # sender (without namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"unknownSender", b"5;"], [b"1", VERSION_B, b"unknownSender", b"N1.COORDINATOR", b"5;", b'[["E", "You did not sign in!"]]']),
    # sender (with given Namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"N1.unknownSender", b"5;"], [b"1", VERSION_B, b"N1.unknownSender", b"N1.COORDINATOR", b"5;", b'[["E", "You did not sign in!"]]']),
    # unknown sender with a rogue node name:
    ([b"1", VERSION_B, b"rec", b"N2.unknownSender", b"5;"], [b"1", VERSION_B, b"N2.unknownSender", b"N1.COORDINATOR", b"5;", b'[["E", "You did not sign in!"]]']),
))
def test_routing_error_messages(coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: Error messages."""
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


@pytest.mark.parametrize("sender", (b"N2.CB", b"N2.COORDINATOR"))
def test_remote_heartbeat(coordinator, fake_counting, sender):
    coordinator.sock._r = [[b"n2", VERSION_B, b"N3.CA", sender, b";"]]
    assert coordinator.node_heartbeats[b"n2"] != 0
    coordinator._routing()
    assert coordinator.node_heartbeats[b"n2"] == 0


class Test_handle_commands:
    """Handle commands sent to the Coordinator."""
    # TODO test individual Coordinator commands and their execution.

    def test_no_response_to_acknowledge(self, coordinator):
        coordinator.sock._r = [[b'123', VERSION_B, b"COORDINATOR", b"rec", b";", b'[["A"]]']]
        coordinator._routing()
        assert coordinator.sock._s == []

    # Sign in / sign out
    def test_signin(self, coordinator):
        coordinator.sock._r = [[b'cb', VERSION_B, b"COORDINATOR", b"CB", b"7;1", b'[["SI"]]']]
        coordinator._routing()  # needs to start at routing, to check that the messages passes the heartbeats
        assert coordinator.sock._s == [[b"cb", VERSION_B, b"CB", b"N1.COORDINATOR", b"7;", b'[["A"]]']]

    def test_signin_rejected(self, coordinator):
        coordinator.sock._r = [[b'cb', VERSION_B, b"COORDINATOR", b"send", b"7;1", b'[["SI"]]']]
        coordinator._routing()
        assert coordinator.sock._s == [[b"cb", VERSION_B, b"send", b"N1.COORDINATOR", b"7;", f'[["{Commands.ERROR}", "{Errors.DUPLICATE_NAME}"]]'.encode()]]

    def test_signout_clears_address(self, coordinator):
        coordinator.sock._r = [[b'123', VERSION_B, b"N1.COORDINATOR", b"rec", b";", b'[["D"]]']]
        coordinator._routing()
        assert b"rec" not in coordinator.directory.keys()
        assert coordinator.sock._s == [[b"123", VERSION_B, b"rec", b"N1.COORDINATOR", b";", b'[["A"]]']]

    def test_signout_requires_signin(self, coordinator):
        coordinator.sock._r = [[b'123', VERSION_B, b"N1.COORDINATOR", b"rec", b";", b'[["D"]]']]
        coordinator._routing()
        coordinator.sock._s = []
        coordinator.sock._r = [[b'123', VERSION_B, b"N1.COORDINATOR", b"rec", b";", b'[["A"]]']]
        coordinator._routing()
        assert coordinator.sock._s == [[b"123", VERSION_B, b"rec", b"N1.COORDINATOR", b";", b'[["E", "You did not sign in!"]]']]

    def test_co_signin_unknown_coordinator_successful(self, coordinator):
        """Test that an unknown Coordinator may sign in."""
        coordinator.sock._r = [[b'n3', VERSION_B, b"COORDINATOR", b"N3.COORDINATOR", b"x;", b'[["COS"]]']]
        coordinator._routing()
        assert b'n3' in coordinator.node_identities.keys()
        assert b"n3" in coordinator.node_heartbeats
        assert coordinator.sock._s == [[b'n3', VERSION_B, b"N3.COORDINATOR", b"N1.COORDINATOR", b"x;", b'[["A"]]']]

    def test_co_signin_known_coordinator_successful(self, coordinator):
        """Test that a Coordinator may sign in as a response to N1's sign in."""
        coordinator.add_coordinator("N3host", 12345)
        coordinator.dealers[b"N3"] = coordinator.dealers.pop(12345)

        coordinator.sock._r = [[b'n3', VERSION_B, b"COORDINATOR", b"N3.COORDINATOR", b"x;", b'[["COS"]]']]
        coordinator._routing()
        assert b'n3' in coordinator.node_identities.keys()
        assert b"n3" in coordinator.node_heartbeats
        assert coordinator.sock._s == [[b'n3', VERSION_B, b"N3.COORDINATOR", b"N1.COORDINATOR", b"x;", b'[["A"]]']]

    def test_co_signin_rejected(self, coordinator):
        """Coordinator sign in rejected due to already connected Coordinator."""
        coordinator.sock._r = [[b'n3', VERSION_B, b"COORDINATOR", b"N2.COORDINATOR", b"x;", b'[["COS"]]']]
        coordinator._routing()
        assert coordinator.sock._s == [[b'n3', VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b"x;", b'[["E", "The name is already taken."]]']]

    def test_co_signout_successful(self, coordinator):
        coordinator.sock._r = [[b'n2', VERSION_B, b"COORDINATOR", b"N2.COORDINATOR", b"x;", b'[["COD"]]']]
        dealer = coordinator.dealers[b"N2"]
        coordinator._routing()
        assert b"n2" not in coordinator.node_identities
        assert dealer._s == [[VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b"x;", b'[["COD"]]']]

    def test_co_signout_of_already_removed_coordinator(self, coordinator):
        # not specified in protocol
        coordinator.sock._r = [[b'n3', VERSION_B, b"COORDINATOR", b"N3.COORDINATOR", b"x;", b'[["COD"]]']]
        coordinator._routing()
        assert not coordinator.sock._s  # no message sent

    def test_co_signout_rejected(self, coordinator):
        coordinator.sock._r = [[b'n4', VERSION_B, b"COORDINATOR", b"N2.COORDINATOR", b"x;", b'[["COD"]]']]
        coordinator._routing()
        assert coordinator.sock._s == [[b"n4", VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b"x;", b'[["E", "Execution of the action failed.", "You are not you!"]]']]

    # Control the Coordinator itself
    def test_shutdown_coordinator(self, coordinator):
        n2dealer = coordinator.dealers[b"N2"]
        coordinator.handle_commands(b'321', b"send", b"N1", b"send", b"7", [b'[["O"]]'])
        assert coordinator.sock._s == [[b'321', VERSION_B, b"send", b"N1.COORDINATOR", b"7;", b'[["A"]]']]  # response
        # Assert sign out messages
        assert n2dealer._s == [[VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b";", b'[["COD"]]']]

    def test_get_directory(self, coordinator):
        coordinator.handle_commands(b'123', b"rec", b"N1", b"rec", b"7", [f'[["{Commands.LIST}"]]'.encode()])
        assert coordinator.sock._s == [[b'123', VERSION_B, b"rec", b"N1.COORDINATOR", b"7;",
                                        b'[["A", {"directory": ["send", "rec"], "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}}]]']]

    def test_set_directory(self, coordinator, fake_counting):
        coordinator.sock._r = [[b"n2", VERSION_B, b"N1.COORDINATOR",
                                b"N2.COORDINATOR", b";", b'[["S", {"directory": ["send", "rec"], "nodes": {"N1": "N1host:12300", "N2": "wrong_host:-7", "N3": "N3host:12300"}}]]']]
        coordinator._routing()
        assert coordinator.global_directory == {b"N2": ["send", "rec"]}
        assert b"N1" not in coordinator.dealers.keys()  # not created
        assert coordinator.node_addresses[b"N2"] == "N2host:12300"  # not changed
        assert b"0.0" in coordinator.dealers.keys()  # newly created
        assert coordinator.dealers[b"N2"]._s == [[VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR",
                                                  b";", b'[["A"]]']]


# Test methods used for command handling
class Test_add_coordinator:
    @pytest.fixture
    def coordinator_added(self, coordinator):
        coordinator.add_coordinator("host", node=12345)
        return coordinator

    def test_socket_created(self, coordinator_added):
        assert coordinator_added.dealers[12345].addr == "tcp://host:12300"

    def test_COS_message_sent(self, coordinator_added):
        assert coordinator_added.dealers[12345]._s == [
            [VERSION_B, b"COORDINATOR", b"N1.COORDINATOR", b";", b'[["COS"]]']]

    def test_address_added(self, coordinator_added):
        assert coordinator_added.node_addresses[12345] == "host:12300"

    def test_waiting_dealer(self, coordinator_added):
        assert 12345 in coordinator_added.waiting_dealers.keys()


class Test_remove_coordinator:
    @pytest.fixture
    def coordinator_removed(self, coordinator):
        coordinator.waiting_dealers[b"N2"] = coordinator.dealers[b"N2"]
        coordinator._test = coordinator.dealers[b"N2"]  # store it for test purposes
        coordinator.remove_coordinator(b"N2", b"n2")
        return coordinator

    def test_socket_closed(self, coordinator_removed):
        assert coordinator_removed._test.addr is None

    def test_socket_removed(self, coordinator_removed):
        assert b"N2" not in coordinator_removed.dealers.keys()

    def test_address_removed(self, coordinator_removed):
        assert b"N2" not in coordinator_removed.node_addresses.keys()

    def test_waiting_dealers_removed(self, coordinator_removed):
        assert b"N2" not in coordinator_removed.waiting_dealers.keys()

    def test_node_identity_removed(self, coordinator_removed):
        assert b"n2" not in coordinator_removed.node_identities.keys()

    def test_node_heartbeats_removed(self, coordinator_removed):
        assert b"n2" not in coordinator_removed.node_heartbeats.keys()


class Test_handle_dealer_message_acknowledge:
    @pytest.fixture
    def c_message_handled(self, coordinator):
        coordinator.add_coordinator("N3host", node=12345)
        sock = coordinator.dealers[12345]
        sock._s = []  # reset effects of add_coordinator
        sock._r = [[VERSION_B, b"N1.COORDINATOR", b"N3.COORDINATOR", b";", b'[["A"]]']]
        coordinator.handle_dealer_message(sock, 12345)
        return coordinator

    def test_dealer_name_changed(self, c_message_handled):
        assert b"N3" in c_message_handled.dealers.keys()
        assert 12345 not in c_message_handled.dealers.keys()

    def test_socket_not_waiting_anymore(self, c_message_handled):
        assert 12345 not in c_message_handled.waiting_dealers.keys()

    def test_address_name_changed(self, c_message_handled):
        assert 12345 not in c_message_handled.node_addresses.keys()
        assert c_message_handled.node_addresses[b"N3"] == "N3host:12300"

    def test_directory_sent(self, c_message_handled):
        assert c_message_handled.dealers[b"N3"]._s == [
            [VERSION_B, b"N3.COORDINATOR", b"N1.COORDINATOR", b";",
             b'[["S", {"directory": ["send", "rec"], "nodes": {"N1": "N1host:12300", "N2": "N2host:12300", "N3": "N3host:12300"}}]]']]


class Test_handle_dealer_message_error:
    @pytest.fixture
    def c_message_handled(self, coordinator):
        coordinator.add_coordinator("N3host", node=12345)
        sock = coordinator.dealers[12345]
        sock._s = []  # reset effects of add_coordinator
        sock._r = [[VERSION_B, b"N1.COORDINATOR", b"N3.COORDINATOR", b";", b'[["E", "The name is already taken."]]']]
        coordinator.handle_dealer_message(sock, 12345)
        return coordinator

    def test_dealer_removed(self, c_message_handled):
        assert 12345 not in c_message_handled.dealers

    def test_socket_not_waiting_anymore(self, c_message_handled):
        assert 12345 not in c_message_handled.waiting_dealers.keys()

    def test_address_name_removed(self):
        pass  # TODO shall the address be removed or not?


def test_sign_out(coordinator):
    n2dealer = coordinator.dealers[b"N2"]
    coordinator.sign_out()
    assert n2dealer._s == [[VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b";", b'[["COD"]]']]
    assert n2dealer.addr is None  # == closed
    assert not coordinator.dealers
