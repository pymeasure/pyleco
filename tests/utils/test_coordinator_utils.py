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

from pyleco.test import FakeContext
from pyleco.core.enums import Commands
from pyleco.core.message import Message
from pyleco.errors import CommunicationError
from pyleco.utils.coordinator_utils import ZmqNode, ZmqMultiSocket, Node, Directory, FakeNode


class TestZmqMultiSocket:
    @pytest.fixture
    def socket(self):
        socket = ZmqMultiSocket(context=FakeContext())  # type: ignore
        socket._sock._r = [[b"id", b"version", b"receiver", b"sender", b"header", b"data"]]  # noqa: E501
        return socket

    def test_poll_True(self, socket):
        assert socket.message_received() is True

    def test_read_message(self, socket):
        assert socket.read_message() == (b"id", Message.from_frames(
            b"version", b"receiver", b"sender", b"header", b"data"))

    def test_poll_False(self, socket):
        socket._sock._r = []
        assert socket.message_received() is False


class TestZmqNode:
    @pytest.fixture
    def node(self):
        node = ZmqNode(context=FakeContext())
        return node

    def test_connection(self, node):
        node.connect("abc")
        assert node._dealer.addr == "tcp://abc"

    def test_disconnect(self, node):
        node.connect("abc")
        socket = node._dealer
        node.disconnect()
        assert socket.addr is None
        assert node.is_connected() is False

    def test_is_connected_with_dealer(self, node):
        node.connect("abc")
        node._dealer.close()
        assert node.is_connected() is False

    def test_is_connected(self, node):
        assert node.is_connected() is False
        node.connect("abc")
        assert node.is_connected() is True


@pytest.fixture
def empty_directory():
    return Directory(b"N1", b"N1.COORDINATOR", "N1host:12300")


@pytest.fixture
def directory(empty_directory):
    d = empty_directory
    d._nodes[b"N2"] = n2 = FakeNode()
    d._node_ids[b"n2"] = n2
    n2.connect("N2host")
    n2.namespace = b"N2"
    d.add_component(b"send", b"send_id")
    d.add_component(b"rec", b"rec_id")
    return d


def fake_perf_counter():
    return 0.


@pytest.fixture()
def fake_counting(monkeypatch):
    monkeypatch.setattr("pyleco.utils.coordinator_utils.perf_counter", fake_perf_counter)


class Test_add_component:
    def test_add_component(self, empty_directory):
        empty_directory.add_component(b"name", b"identity")
        assert b"name" in empty_directory.get_components()
        assert empty_directory.get_components()[b"name"].identity == b"identity"

    def test_reject_adding(self, directory):
        with pytest.raises(ValueError):
            directory.add_component(b"send", b"identity")
        assert directory.get_components()[b"send"].identity != b"identity"


class Test_remove_component:
    @pytest.mark.parametrize("identity", (b"", b"send_id"))
    def test_remove(self, directory, identity):
        directory.remove_component(b"send", identity)
        assert b"send" not in directory.get_components()

    def test_remove_with_wrong_identity(self, directory):
        with pytest.raises(ValueError):
            directory.remove_component(b"send", b"wrong_identity")

    def test_remove_not_present(self, directory):
        """Test whether an already removed component does not raise an error."""
        directory.remove_component(b"not_present", b"")


class Test_get_component_id:
    def test_component_present(self, directory):
        assert directory.get_component_id(b"send") == b"send_id"

    def test_component_missing(self, directory):
        with pytest.raises(ValueError):
            directory.get_component_id(b"not_present")


class Test_add_node_sender:
    @pytest.mark.parametrize("namespace", (b"N1", b"N2"))
    def test_invalid_namespaces(self, directory, namespace):
        with pytest.raises(ValueError):
            directory.add_node_sender(Node(), "N3host", namespace)

    @pytest.mark.parametrize("address", ("N1host", "N3host", "N1host:12300", "N3host:12300"))
    def test_invalid_address(self, directory, address):
        with pytest.raises(ValueError):
            directory._waiting_nodes["N3host:12300"] = None  # already trying to connect to
            directory.add_node_sender(Node(), address, b"N3")

    def test_node_added(self, fake_counting, directory):
        length = len(directory._waiting_nodes)
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        assert directory._nodes.get(b"N3") is None
        assert len(directory._waiting_nodes) > length

    @pytest.fixture
    def node(self, directory):
        directory.add_node_sender(FakeNode(), "N3host:12345", b"N3")
        return directory._waiting_nodes[list(directory._waiting_nodes.keys())[0]]

    def test_node_address(self, node):
        assert node.address == "N3host:12345"

    def test_node_heartbeat(self, fake_counting, node):
        assert node.heartbeat == 0

    def test_node_connected(self, node):
        assert node.is_connected()

    def test_message_sent(self, node):
        assert node._messages_sent == [Message(b"COORDINATOR", b"N1.COORDINATOR",
                                               [[Commands.CO_SIGNIN]])]

    def test_node_port_added_to_address(self, directory):
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        assert directory._waiting_nodes["N3host:12300"].address == "N3host:12300"


class Test_add_node_receiver:
    pass  # TODO


class Test_check_unfinished_node_connections:
    @pytest.fixture
    def directory_cunc(self, directory):
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        node = directory._waiting_nodes["N3host:12300"]
        node._messages_read = [Message(b"N1.COORDINATOR", b"N3.COORDINATOR",
                                       data=[[Commands.ACKNOWLEDGE]])]
        directory.check_unfinished_node_connections()
        return directory

    def test_new_node(self, directory_cunc):
        assert directory_cunc.get_node(b"N3") is not None


class Test_handle_node_message:
    pass  # TODO


class Test_finish_sign_in_to_remote:
    @pytest.fixture
    def directory_sirn(self, directory):
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        temp_namespace = list(directory._waiting_nodes.keys())[0]
        node = directory._waiting_nodes[temp_namespace]
        assert node.namespace != b"N3"
        directory._finish_sign_in_to_remote(temp_namespace, Message(
            receiver=b"N1.COORDINATOR",
            sender=b"N3.COORDINATOR",
            data=[[Commands.ACKNOWLEDGE]],
        ))
        return directory

    def test_waiting_nodes_cleared(self, directory_sirn):
        assert len(directory_sirn._waiting_nodes) == 0

    def test_node_renamed(self, directory_sirn):
        assert list(directory_sirn._nodes.keys()) == [b"N2", b"N3"]

    def test_node_namespace_set(self, directory_sirn):
        assert directory_sirn._nodes[b"N3"].namespace == b"N3"

    def test_directory_sent(self, directory_sirn):
        assert directory_sirn._nodes[b"N3"]._messages_sent == [
            Message(b'COORDINATOR', b'N1.COORDINATOR', [[Commands.CO_SIGNIN]]),
            Message(
                b'N3.COORDINATOR', b'N1.COORDINATOR',
                [[Commands.SET, {
                    "directory": ["send", "rec"],
                    "nodes": {"N1": "N1host:12300", "N2": "N2host", "N3": "N3host:12300"}}]]
            )]


class Test_combine_sender_and_receiver_nodes:
    @pytest.fixture
    def directory_crasn(self, directory):
        directory.add_node_receiver(b"n3", b"N3")
        return directory

    def test_match(self, directory_crasn):
        node = Node()
        node.namespace = b"N3"
        directory_crasn._combine_sender_and_receiver_nodes(node)
        assert node.heartbeat != -1
        assert directory_crasn._node_ids[b"n3"] == node

    def test_mismatch(self, directory_crasn):
        node = Node()
        node.namespace = b"N4"
        directory_crasn._combine_sender_and_receiver_nodes(node)
        assert node.heartbeat == -1
        assert directory_crasn._node_ids[b"n3"] != node


class Test_remove_node_without_checks:
    def test_remove_only_receiver(self, directory):
        directory.add_node_receiver(b"n3", b"N3")
        assert b"n3" in directory._node_ids
        directory._remove_node_without_checks(b"N3")
        assert b"n3" not in directory._node_ids
        assert b"N3" not in directory._nodes

    def test_remove_complete_node(self, directory):
        assert b"n2" in directory._node_ids
        assert b"N2" in directory._nodes
        directory._remove_node_without_checks(b"N2")
        assert b"n2" not in directory._node_ids
        assert b"N2" not in directory._nodes

    def test_remove_by_namespace(self, directory):
        node = Node()
        directory._nodes[b"N3"] = node
        directory._node_ids[b"some_id"] = node
        directory._remove_node_without_checks(b"N3")
        assert b"some_id" not in directory._node_ids
        assert b"N3" not in directory._nodes


class Test_update_heartbeat:
    def test_local_component(self, fake_counting, directory):
        directory.update_heartbeat(b"send_id", Message.from_frames(b"", b"", b"N1.send", b""))
        assert directory.get_components()[b"send"].heartbeat == 0

    def test_local_component_without_namespace(self, fake_counting, directory):
        directory.update_heartbeat(b"send_id", Message.from_frames(b"", b"", b"send", b""))
        assert directory.get_components()[b"send"].heartbeat == 0

    def test_local_component_signs_in(self, directory):
        directory.update_heartbeat(b"new_id", Message.from_frames(
            b"", b"COORDINATOR", b"send", b"",
            f'[["{Commands.SIGNIN}"]]'.encode()))
        # test that no error is raised

    def test_local_component_with_wrong_id(self, directory):
        with pytest.raises(CommunicationError):
            directory.update_heartbeat(b"new_id", Message.from_frames(
                b"", b"COORDINATOR", b"send", b""))

    def test_known_node(self, fake_counting, directory):
        directory.update_heartbeat(b"n2", Message.from_frames(b"", b"COORDINATOR", b"N2.send", b""))
        assert directory.get_node_ids()[b"n2"].heartbeat == 0

    def test_signing_in_node(self, directory):
        directory.update_heartbeat(b"n3", Message(
            b"COORDINATOR", b"N3.COORDINATOR", [[Commands.CO_SIGNIN]]))
        # test that no error is raised

    def test_signing_out_node(self, directory):
        directory.update_heartbeat(b"n3", Message(
            b"COORDINATOR", b"N3.COORDINATOR", [[Commands.CO_SIGNOUT]]))
        # test that no error is raised

    def test_unknown_node(self, directory):
        with pytest.raises(CommunicationError):
            directory.update_heartbeat(b"n3", Message(b"COORDINATOR", b"N3.send"))


class Test_find_expired_components:
    def test_expired_component(self, directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -3.5
        directory.find_expired_components(1)
        assert b"send" not in directory.get_components().keys()

    def test_warn_component(self, directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -1.5
        assert directory.find_expired_components(1) == [(b"send_id", b"send")]

    def test_active_Component(self, directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -0.5
        assert directory.find_expired_components(1) == []
        assert b"send" in directory.get_components()


class Test_find_expired_nodes:

    def test_expired_node(self, directory, fake_counting):
        directory.get_node_ids()[b"n2"].heartbeat = -3.5
        directory.find_expired_nodes(1)
        assert b"n2" not in directory.get_node_ids()

    def test_warn_node(self, directory, fake_counting):
        directory.get_node_ids()[b"n2"].heartbeat = -1.5
        directory.find_expired_nodes(1)
        assert directory.get_node_ids()[b"n2"]._messages_sent == [
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR", [[Commands.PING]])]

    def test_active_node(self, directory, fake_counting):
        directory.get_node_ids()[b"n2"].heartbeat = -0.5
        directory.find_expired_nodes(1)
        assert b"n2" in directory.get_node_ids()


class Test_sign_out_from_node:
    @pytest.fixture
    def directory_wo_n2(self, directory):
        directory._test = directory.get_node(b"N2")
        directory.sign_out_from_node(b"N2")
        return directory

    def test_message_sent(self, directory_wo_n2):
        assert directory_wo_n2._test._messages_sent == [
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR", [[Commands.CO_SIGNOUT]])]

    def test_connection_closed(self, directory_wo_n2):
        assert directory_wo_n2._test.is_connected() is False

    def test_n2_removed_from_nodes(self, directory_wo_n2):
        assert b"N2" not in directory_wo_n2.get_nodes()

    def test_n2_removed_from_node_ids(self, directory_wo_n2):
        assert b"n2" not in directory_wo_n2.get_node_ids()
