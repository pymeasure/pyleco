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

from pyleco.core import VERSION_B
from pyleco.core.enums import Commands, Errors
from pyleco.core.message import Message
from pyleco.utils.coordinator_utils import FakeMultiSocket, FakeNode
from pyleco.test import FakeContext

from pyleco.coordinators.coordinator import Coordinator


@pytest.fixture
def coordinator():
    coordinator = Coordinator(namespace="N1", host="N1host", cleaning_interval=1e5,
                              context=FakeContext(),  # type: ignore
                              multi_socket=FakeMultiSocket()
                              )
    d = coordinator.directory
    d.add_component(b"send", b"321")
    d.add_component(b"rec", b"123")
    d.add_node_sender(FakeNode(), "N2host:12300", namespace=b"N2")
    d._nodes[b"N2"] = d._waiting_nodes.pop("N2host:12300")
    d._nodes[b"N2"].namespace = b"N2"
    d._waiting_nodes = {}
    d.add_node_receiver(b"n2", b"N2")
    n2 = coordinator.directory.get_node(b"N2")
    n2._messages_sent = []  # type: ignore # reset dealer sock._socket.
    n2.heartbeat = -1
    coordinator.sock._messages_sent = []  # type: ignore reset router sock._socket
    return coordinator


def fake_perf_counter():
    return 0.


@pytest.fixture()
def fake_counting(monkeypatch):
    # TODO adjust to pyleco
    monkeypatch.setattr("pyleco.utils.coordinator_utils.perf_counter", fake_perf_counter)


class Test_clean_addresses:
    def test_expired_component(self, coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -3.5
        coordinator.clean_addresses(1)
        assert b"send" not in coordinator.directory.get_component_names()

    def test_expired_component_updates_directory(self, coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -3.5
        coordinator.clean_addresses(1)
        assert coordinator.directory.get_nodes()[b"N2"]._messages_sent == [
            Message(
                receiver=b"N2.COORDINATOR", sender=b"N1.COORDINATOR",
                data=[["S", {"directory": ["rec"],
                             "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}}]])
        ]

    def test_warn_component(self, coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -1.5
        coordinator.clean_addresses(1)
        assert coordinator.sock._messages_sent == [(b"321", Message(
            b"N1.send", b"N1.COORDINATOR", [["P"]]))]

    def test_active_Component(self, coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -0.5
        coordinator.clean_addresses(1)
        assert coordinator.sock._messages_sent == []
        assert b"send" in coordinator.directory.get_components()

    def test_expired_Coordinator(self, coordinator, fake_counting):
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -3.5
        coordinator.clean_addresses(1)
        assert b"n2" not in coordinator.directory.get_node_ids()
        # further removal tests in :class:`Test_remove_coordinator`

    def test_warn_Coordinator(self, coordinator, fake_counting):
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -1.5
        coordinator.clean_addresses(1)
        assert coordinator.directory.get_node_ids()[b"n2"]._messages_sent == [
            Message(
                b'N2.COORDINATOR', b'N1.COORDINATOR',
                [["S", {"directory": ["send", "rec"],
                        "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}}]]),
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR", [["P"]]),
        ]

    def test_active_Coordinator(self, coordinator, fake_counting):
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -0.5
        coordinator.clean_addresses(1)
        assert b"n2" in coordinator.directory.get_node_ids()


def test_heartbeat_local(fake_counting, coordinator):
    coordinator.sock._messages_read = [[b"321", Message(b"COORDINATOR", b"send")]]
    coordinator.read_and_route()
    assert coordinator.directory.get_components()[b"send"].heartbeat == 0


@pytest.mark.parametrize("i, o", (
    ([b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""], None),  # test heartbeat alone
    ([b"321", VERSION_B, b"rec", b"send", b";", b"1"],
     [b"123", VERSION_B, b"rec", b"send", b";", b"1"]),  # receiver known, sender known.
))
def test_routing_successful(coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: successful routing."""
    coordinator.sock._messages_read = [(i[0], Message.from_frames(*i[1:]))]
    coordinator.read_and_route()
    if o is None:
        assert coordinator.sock._messages_sent == []
    else:
        assert coordinator.sock._messages_sent == [(o[0], Message.from_frames(*o[1:]))]


@pytest.mark.parametrize("i, o", (
    # receiver unknown, return to sender:
    ([b"321", VERSION_B, b"x", b"send", b";", b""],
     [b"321", VERSION_B, b"send", b"N1.COORDINATOR", b";",
      b'[["E", "Receiver is not in addresses list.", "x"]]']),
    # unknown receiver node:
    ([b"321", VERSION_B, b"N3.CB", b"N1.send", b";"],
     [b"321", VERSION_B, b"N1.send", b"N1.COORDINATOR", b";",
      b'[["E", "Node is not known.", "N3"]]']),
    # sender (without namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"unknownSender", b"5;"],
     [b"1", VERSION_B, b"unknownSender", b"N1.COORDINATOR", b"5;",
      b'[["E", "You did not sign in!"]]']),
    # sender (with given Namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"N1.unknownSender", b"5;"],
     [b"1", VERSION_B, b"N1.unknownSender", b"N1.COORDINATOR", b"5;",
      b'[["E", "You did not sign in!"]]']),
    # unknown sender with a rogue node name:
    ([b"1", VERSION_B, b"rec", b"N2.unknownSender", b"5;"],
     [b"1", VERSION_B, b"N2.unknownSender", b"N1.COORDINATOR", b"5;",
      b'[["E", "You did not sign in!"]]']),
))
def test_routing_error_messages(coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: Error messages."""
    coordinator.sock._messages_read = [(i[0], Message.from_frames(*i[1:]))]
    coordinator.read_and_route()
    if o is None:
        assert coordinator.sock._messages_sent == []
    else:
        assert coordinator.sock._messages_sent == [(o[0], Message.from_frames(*o[1:]))]


def test_remote_routing(coordinator):
    coordinator.sock._messages_read = [[b"321", Message(b"N2.CB", b"N1.send")]]
    coordinator.read_and_route()
    assert coordinator.directory.get_node(b"N2")._messages_sent == [
        Message(b"N2.CB", b"N1.send")]


@pytest.mark.parametrize("sender", (b"N2.CB", b"N2.COORDINATOR"))
def test_remote_heartbeat(coordinator, fake_counting, sender):
    coordinator.sock._messages_read = [[b"n2", Message(b"N3.CA", sender)]]
    assert coordinator.directory.get_node_ids()[b"n2"].heartbeat != 0
    coordinator.read_and_route()
    assert coordinator.directory.get_node_ids()[b"n2"].heartbeat == 0


class Test_handle_commands:
    """Handle commands sent to the Coordinator."""
    # TODO test individual Coordinator commands and their execution.

    def test_no_response_to_acknowledge(self, coordinator):
        coordinator.sock._messages_read = [[b'123', Message(
            b"COORDINATOR", b"rec", [[Commands.ACKNOWLEDGE]])]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == []

    # Sign in / sign out
    def test_signin(self, coordinator):
        coordinator.sock._messages_read = [[b'cb', Message(b"COORDINATOR", b"CB",
                                                           data=[[Commands.SIGNIN]],
                                                           conversation_id=b"7",
                                                           message_id=b"1",
                                                           )]]
        # read_and_route needs to start at routing, to check that the messages passes the heartbeats
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [
            (b"cb", Message(b"CB", b"N1.COORDINATOR",
                            conversation_id=b"7",
                            data=[[Commands.ACKNOWLEDGE]]))]

    def test_signin_sends_directory_update(self, coordinator):
        coordinator.sock._messages_read = [[b'cb', Message(b"COORDINATOR", b"CB",
                                                           data=[[Commands.SIGNIN]],
                                                           conversation_id=b"7",
                                                           message_id=b"1",
                                                           )]]
        # read_and_route needs to start at routing, to check that the messages passes the heartbeats
        coordinator.read_and_route()
        assert coordinator.directory.get_node(b"N2")._messages_sent == [Message(
            b"N2.COORDINATOR", b"N1.COORDINATOR",
            data=[["S", {"directory": ["send", "rec", "CB"],
                         "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}}]]
        )]

    def test_signin_rejected(self, coordinator):
        coordinator.sock._messages_read = [[b'cb', Message(b"COORDINATOR", b"send",
                                                           data=[[Commands.SIGNIN]],
                                                           conversation_id=b"7",
                                                           message_id=b"1",
                                                           )]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"cb", Message(
            b"send", b"N1.COORDINATOR",
            conversation_id=b"7",
            data=[[Commands.ERROR, Errors.DUPLICATE_NAME]]
        ))]

    def test_signout_clears_address(self, coordinator):
        coordinator.sock._messages_read = [[b'123', Message(
            b"N1.COORDINATOR", b"rec", [[Commands.SIGNOUT]])]]
        coordinator.read_and_route()
        assert b"rec" not in coordinator.directory.get_components().keys()
        assert coordinator.sock._messages_sent == [
            (b"123", Message(b"rec", b"N1.COORDINATOR", data=[[Commands.ACKNOWLEDGE]]))]

    def test_signout_clears_address_explicit_namespace(self, coordinator):
        coordinator.sock._messages_read = [[b'123', Message(
            b"N1.COORDINATOR", b"N1.rec", [[Commands.SIGNOUT]])]]
        coordinator.read_and_route()
        assert b"rec" not in coordinator.directory.get_components().keys()
        assert coordinator.sock._messages_sent == [
            (b"123", Message(b"N1.rec", b"N1.COORDINATOR", [[Commands.ACKNOWLEDGE]]))]

    def test_signout_sends_directory_update(self, coordinator):
        coordinator.sock._messages_read = [[b'123', Message(
            b"N1.COORDINATOR", b"rec", [[Commands.SIGNOUT]])]]
        coordinator.read_and_route()
        assert coordinator.directory.get_node(b"N2")._messages_sent == [Message(
            b"N2.COORDINATOR", b"N1.COORDINATOR",
            data=[["S", {"directory": ["send"],
                         "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}}]])]

    def test_signout_requires_new_signin(self, coordinator):
        coordinator.sock._messages_read = [[b'123', Message(
            b"N1.COORDINATOR", b"rec", [[Commands.SIGNOUT]])]]
        coordinator.read_and_route()  # handle signout
        coordinator.sock._messages_sent = []
        coordinator.sock._messages_read = [[b'123', Message(
            b"N1.COORDINATOR", b"rec", [[Commands.ACKNOWLEDGE]])]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"123", Message(
            b"rec", b"N1.COORDINATOR", [[Commands.ERROR, Errors.NOT_SIGNED_IN]]))]

    def test_co_signin_unknown_coordinator_successful(self, coordinator):
        """Test that an unknown Coordinator may sign in."""
        coordinator.sock._messages_read = [
            [b'n3', Message(b"COORDINATOR", b"N3.COORDINATOR",
                            data=[[Commands.CO_SIGNIN]],
                            conversation_id=b"x")]]
        coordinator.read_and_route()
        assert b'n3' in coordinator.directory.get_node_ids().keys()
        assert coordinator.sock._messages_sent == [
            (b'n3', Message(b"N3.COORDINATOR", b"N1.COORDINATOR",
                            conversation_id=b"x", data=[[Commands.ACKNOWLEDGE]]))]

    def test_co_signin_known_coordinator_successful(self, fake_counting, coordinator):
        """Test that a Coordinator may sign in as a response to N1's sign in."""

        coordinator.directory.add_node_sender(FakeNode(), "N3host:12345", namespace=b"N3")
        coordinator.directory.get_nodes()[b"N3"] = coordinator.directory._waiting_nodes.pop(
            "N3host:12345")
        coordinator.directory.get_nodes()[b"N3"].namespace = b"N3"

        coordinator.sock._messages_read = [
            [b'n3', Message(b"COORDINATOR", b"N3.COORDINATOR",
                            conversation_id=b"x", data=[[Commands.CO_SIGNIN]])]]
        coordinator.read_and_route()
        assert b'n3' in coordinator.directory.get_node_ids().keys()
        assert coordinator.sock._messages_sent == [(b'n3', Message(
            b"N3.COORDINATOR", b"N1.COORDINATOR", [[Commands.ACKNOWLEDGE]], conversation_id=b"x"))]

    def test_co_signin_rejected(self, coordinator):
        """Coordinator sign in rejected due to already connected Coordinator."""
        coordinator.sock._messages_read = [
            [b'n3', Message(b"COORDINATOR", b"N2.COORDINATOR",
                            [[Commands.CO_SIGNIN]], conversation_id=b"x")]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"n3", Message(
            b"N2.COORDINATOR", b"N1.COORDINATOR", data=[[Commands.ERROR, Errors.DUPLICATE_NAME]],
            conversation_id=b"x"))]

    def test_co_signin_of_self_rejected(self, coordinator):
        """Coordinator sign in rejected because it is the same coordinator."""
        coordinator.sock._messages_read = [
            [b'n3', Message(b"COORDINATOR", b"N1.COORDINATOR",
                            conversation_id=b"x", data=[[Commands.CO_SIGNIN]])]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [
            (b'n3', Message.from_frames(VERSION_B, b"N1.COORDINATOR", b"N1.COORDINATOR", b"x;",
             b'[["E", "You did not sign in!"]]'))]  # TODO should be "The name is already taken

    def test_co_signout_successful(self, coordinator):
        coordinator.sock._messages_read = [
            [b'n2', Message(b"COORDINATOR", b"N2.COORDINATOR",
                            conversation_id=b"x", data=[[Commands.CO_SIGNOUT]])]]
        node = coordinator.directory.get_node(b"N2")
        coordinator.read_and_route()
        assert b"n2" not in coordinator.directory.get_node_ids()
        assert node._messages_sent == [Message(
            b"N2.COORDINATOR", b"N1.COORDINATOR", conversation_id=b"x",
            data=[[Commands.CO_SIGNOUT]])]

    def test_co_signout_rejected(self, coordinator):
        coordinator.sock._messages_read = [
            [b'n4', Message.from_frames(VERSION_B, b"COORDINATOR", b"N2.COORDINATOR",
                                        b"x;", b'[["COD"]]')]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [
            (b"n4", Message.from_frames(VERSION_B, b"N2.COORDINATOR", b"N1.COORDINATOR", b"x;",
             b'[["E", "Execution of the action failed.", "You are not you!"]]'))]

    def test_co_signout_of_not_signed_in(self, coordinator):
        """TBD whether to reject or to ignore."""
        coordinator.sock._messages_read = [
            (b"n4", Message(b"COORDINATOR", b"N4.COORDINATOR", [[Commands.CO_SIGNOUT]]))]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == []

    # Control the Coordinator itself
    def test_shutdown_coordinator(self, coordinator):
        n2 = coordinator.directory.get_node(b"N2")
        coordinator.handle_commands(b'321', Message.from_frames(
            b"send", b"N1", b"send", b"7;", b'[["O"]]'))
        assert coordinator.sock._messages_sent == [
            (b'321', Message.from_frames(
                VERSION_B, b"send", b"N1.COORDINATOR", b"7;", b'[["A"]]'))]  # response
        # Assert sign out messages
        assert n2._messages_sent == [
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR", [[Commands.CO_SIGNOUT]])]

    def test_get_global_directory(self, coordinator):
        coordinator.global_directory[b"N5"] = ["some", "coordinator"]
        coordinator.handle_commands(b'123', Message.from_frames(b"rec", b"N1", b"rec", b"7;",
                                    f'[["{Commands.LIST}"]]'.encode()))
        assert coordinator.sock._messages_sent == [
            (b'123', Message(b"rec", b"N1.COORDINATOR", conversation_id=b"7",
             data=[[Commands.ACKNOWLEDGE, {
                 "N5": ["some", "coordinator"],
                 "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"},
                 "N1": ["send", "rec"]}]]))]

    def test_set_directory(self, coordinator, fake_counting):
        # TODO whether full directories or diffs are acceptable, is TBD.
        coordinator.sock._messages_read = [(b"n2", Message(
            b"N1.COORDINATOR", b"N2.COORDINATOR",
            data=[[Commands.SET, {
                "directory": ["send", "rec"],
                "nodes": {"N1": "N1host:12300", "N2": "wrong_host:-7", "N3": "N3host:12300"},
            }]]))]
        coordinator.read_and_route()
        assert coordinator.global_directory == {b"N2": ["send", "rec"]}
        assert coordinator.directory.get_node(b"N2").address == "N2host:12300"  # not changed
        assert "N3host:12300" in coordinator.directory._waiting_nodes.keys()  # newly created
        assert coordinator.directory.get_node(b"N2")._messages_sent == [Message(
            b"N2.COORDINATOR", b"N1.COORDINATOR", [[Commands.ACKNOWLEDGE]])]

    def test_get_local_directory(self, coordinator):
        coordinator.handle_commands(b'123', Message(
            b"N1.COORDINATOR", b"rec", conversation_id=b"7",
            data=[[Commands.GET, ["directory", "nodes"]]]))
        assert coordinator.sock._messages_sent == [(b'123', Message(
            b"rec", b"N1.COORDINATOR", conversation_id=b"7", data=[[Commands.ACKNOWLEDGE, {
                "directory": ["send", "rec"], "nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}
            }]]))]


# Test methods used for command handling
