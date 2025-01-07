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

import pytest

from pyleco.test import FakeContext
from pyleco.core.message import Message, MessageTypes
from pyleco.json_utils.errors import NOT_SIGNED_IN, DUPLICATE_NAME
from pyleco.json_utils.json_objects import Request, ResultResponse, ErrorResponse
from pyleco.utils.coordinator_utils import CommunicationError, ZmqNode, ZmqMultiSocket, Node,\
    Directory, FakeNode


class TestZmqMultiSocket:
    @pytest.fixture
    def socket(self):
        socket = ZmqMultiSocket(context=FakeContext())  # type: ignore
        socket._sock._r = [  # type: ignore
            [b"id", b"version", b"receiver", b"sender", b"header", b"data"]]
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
        node = ZmqNode(context=FakeContext())  # type: ignore
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


cid = b"conversation_id;"


def fake_generate_cid():
    return cid


@pytest.fixture()
def fake_cid_generation(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


@pytest.fixture
def empty_directory() -> Directory:
    return Directory(b"N1", b"N1.COORDINATOR", "N1host:12300")


@pytest.fixture
def directory(empty_directory: Directory) -> Directory:
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
    def test_add_component(self, empty_directory: Directory):
        empty_directory.add_component(b"name", b"identity")
        assert b"name" in empty_directory.get_components()
        assert empty_directory.get_components()[b"name"].identity == b"identity"

    def test_adding_component_of_already_signed_in_component_succeeds(self, fake_counting,
                                                                      directory: Directory):
        # TODO not defined in LECO
        sender = directory._components[b"send"]
        sender.heartbeat = -100
        directory.add_component(name=b"send", identity=b"send_id")
        # test that no error is raised.
        assert sender.heartbeat == 0

    def test_reject_adding(self, directory: Directory):
        with pytest.raises(ValueError):
            directory.add_component(b"send", b"new_identity")
        assert directory.get_components()[b"send"].identity != b"new_identity"


class Test_remove_component:
    @pytest.mark.parametrize("identity", (b"", b"send_id"))
    def test_remove(self, directory: Directory, identity):
        directory.remove_component(b"send", identity)
        assert b"send" not in directory.get_components()

    def test_remove_with_wrong_identity(self, directory: Directory):
        with pytest.raises(ValueError):
            directory.remove_component(b"send", b"wrong_identity")

    def test_remove_not_present(self, directory: Directory):
        """Test whether an already removed component does not raise an error."""
        directory.remove_component(b"not_present", b"")


class Test_get_component_id:
    def test_component_present(self, directory: Directory):
        assert directory.get_component_id(b"send") == b"send_id"

    def test_component_missing(self, directory: Directory):
        with pytest.raises(ValueError):
            directory.get_component_id(b"not_present")


class Test_add_node_sender:
    """These are the first two parts of the sign in process: connect and send the COSIGNIN."""
    @pytest.mark.parametrize("namespace", (b"N1", b"N2"))
    def test_invalid_namespaces(self, directory: Directory, namespace):
        with pytest.raises(ValueError):
            directory.add_node_sender(Node(), "N3host", namespace)

    @pytest.mark.parametrize("address", ("N1host", "N3host", "N1host:12300", "N3host:12300"))
    def test_invalid_address(self, directory: Directory, address):
        """No new connection to the coordinator itself or if there is another attempt to connect
        to that same remote node."""
        # simulate a connection to N3 under way
        directory._waiting_nodes["N3host:12300"] = None  # type: ignore
        with pytest.raises(ValueError):
            directory.add_node_sender(Node(), address, b"N3")

    def test_node_added(self, fake_counting, directory: Directory):
        length = len(directory._waiting_nodes)
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        assert directory._nodes.get(b"N3host") is None
        assert len(directory._waiting_nodes) > length

    @pytest.fixture
    def node(self, fake_cid_generation, directory: Directory) -> Node:
        address = "N3host:12345"
        directory.add_node_sender(node=FakeNode(), address=address, namespace=b"N3")
        return directory._waiting_nodes[address]

    def test_node_address(self, node: Node):
        assert node.address == "N3host:12345"

    def test_node_heartbeat(self, fake_counting, node: Node):
        assert node.heartbeat == 0

    def test_node_connected(self, node: Node):
        assert node.is_connected()

    def test_message_sent(self, node: Node):
        assert node._messages_sent == [Message(  # type: ignore
            b"COORDINATOR", b"N1.COORDINATOR",
            data=Request(id=1, method="coordinator_sign_in"),
            message_type=MessageTypes.JSON,
            conversation_id=cid)]

    def test_node_port_added_to_address(self, directory: Directory):
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        assert directory._waiting_nodes["N3host:12300"].address == "N3host:12300"


class Test_add_node_receiver_unknown:
    """Handles a remote Coordinator, which is signing in."""
    @pytest.fixture
    def unknown_node(self, fake_counting, directory: Directory) -> Node:
        identity = b"receiver_id"
        directory.add_node_receiver(identity=identity, namespace=b"N3")
        return directory._node_ids[identity]

    def test_namespace_with_identity(self, unknown_node: Node):
        assert unknown_node.namespace == b"N3"

    def test_heartbeat(self, unknown_node: Node):
        assert unknown_node.heartbeat == 0


class Test_add_node_receiver_partially_known:
    identity = b"n3"

    @pytest.fixture
    def partially_known_node(self, fake_counting, directory: Directory) -> Directory:
        """Only sending to that node is possible."""
        node = FakeNode()
        node.namespace = b"N3"
        directory._nodes[node.namespace] = node
        directory.add_node_receiver(identity=self.identity, namespace=b"N3")
        return directory

    def test_heartbeat(self, partially_known_node: Directory):
        assert partially_known_node._node_ids[self.identity].heartbeat == 0

    def test_id_set(self, partially_known_node: Directory):
        assert self.identity in partially_known_node._node_ids.keys()


def test_add_node_receiver_already_known(directory: Directory):
    with pytest.raises(ValueError):
        directory.add_node_receiver(b"n5", b"N2")


class Test_check_unfinished_node_connections:
    @pytest.fixture
    def directory_cunc(self, directory: Directory) -> Directory:
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        node = directory._waiting_nodes["N3host:12300"]
        node._messages_read = [Message(b"N1.COORDINATOR", b"N3.COORDINATOR",  # type: ignore
                                       message_type=MessageTypes.JSON,
                                       data=ResultResponse(id=1, result=None))]
        directory.check_unfinished_node_connections()
        return directory

    def test_new_node(self, directory_cunc: Directory):
        assert directory_cunc.get_node(b"N3") is not None


def test_check_unfinished_node_connection_logs_error(directory: Directory, caplog):
    directory.add_node_sender(FakeNode(), "N3host", b"N3")
    node = directory._waiting_nodes["N3host:12300"]

    def read_message(timeout: int = 0) -> Message:
        return Message.from_frames(*[b"frame 1", b"frame 2"])  # not enough frames
    node.read_message = read_message  # type: ignore
    node._messages_read = ["just something to indicate a message in the buffer"]  # type: ignore
    directory.check_unfinished_node_connections()
    assert caplog.records[-1].msg == "Message decoding failed."


class Test_handle_node_message:
    """Already included in check_unfinished_node_connections"""
    @pytest.mark.parametrize("message", (
            Message(b"N1.COORDINATOR", b"N5.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data=ErrorResponse(id=None, error=DUPLICATE_NAME)),
            Message(b"N1.COORDINATOR", b"N5.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data=ErrorResponse(id=None, error=NOT_SIGNED_IN)),
            Message("N1.COORDINATOR", "N5.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data={"jsonrpc": "2.0", "error": {"code": -32600, "message": "Invalid Request"},
                          "id": None})
    ))
    def test_rejected_sign_in(self, directory: Directory, message):
        directory._waiting_nodes["N5host"] = n = FakeNode()
        directory._handle_node_message(key="N5host", message=message)
        assert "N5host" not in directory._waiting_nodes.keys()
        assert n not in directory._nodes.values()

    @pytest.mark.parametrize("message", (
            Message(b"N1.COORDINATOR", b"N5.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data={"jsonrpc": "2.0", "result": None, "id": 1}),
            Message(b"N1.COORDINATOR", b"N5.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data={"jsonrpc": "2.0", "result": None, "id": 5}),
    ))
    def test_successful_sign_in(self, directory: Directory, message):
        directory._waiting_nodes["N5host"] = n = FakeNode()
        directory._handle_node_message(key="N5host", message=message)
        assert directory.get_node(b"N5") == n
        assert "N5host" not in directory._waiting_nodes.keys()


class Test_finish_sign_in_to_remote:
    @pytest.fixture
    def directory_sirn(self, fake_cid_generation, directory: Directory) -> Directory:
        directory.add_node_sender(FakeNode(), "N3host", b"N3")
        temp_namespace = list(directory._waiting_nodes.keys())[0]
        node = directory._waiting_nodes[temp_namespace]
        assert node.namespace != b"N3"
        directory._finish_sign_in_to_remote(temp_namespace, Message(
            receiver=b"N1.COORDINATOR",
            sender=b"N3.COORDINATOR",
            message_type=MessageTypes.JSON,
            data={"id": 1, "result": None, "jsonrpc": "2.0"},
        ))
        return directory

    def test_waiting_nodes_cleared(self, directory_sirn: Directory):
        assert len(directory_sirn._waiting_nodes) == 0

    def test_node_renamed(self, directory_sirn: Directory):
        assert list(directory_sirn._nodes.keys()) == [b"N2", b"N3"]

    def test_node_namespace_set(self, directory_sirn: Directory):
        assert directory_sirn._nodes[b"N3"].namespace == b"N3"

    def test_directory_sent(self, directory_sirn: Directory):
        assert directory_sirn._nodes[b"N3"]._messages_sent == [  # type: ignore
            Message(b'COORDINATOR', b'N1.COORDINATOR',
                    {"id": 1, "method": "coordinator_sign_in", "jsonrpc": "2.0"},
                    message_type=MessageTypes.JSON,
                    conversation_id=cid),
            Message(
                b'N3.COORDINATOR', b'N1.COORDINATOR',
                data=[{"id": 2, "method": "add_nodes", "params":
                       {"nodes": {"N1": "N1host:12300", "N2": "N2host", "N3": "N3host:12300"}},
                       "jsonrpc": "2.0"},
                      {"id": 3, "method": "record_components", "params":
                       {"components": ["send", "rec"]}, "jsonrpc": "2.0"}],
                message_type=MessageTypes.JSON,
                conversation_id=cid,
            )]


class Test_combine_sender_and_receiver_nodes:
    @pytest.fixture
    def directory_crasn(self, directory: Directory) -> Directory:
        directory.add_node_receiver(b"n3", b"N3")
        return directory

    def test_match(self, directory_crasn: Directory):
        node = Node()
        node.namespace = b"N3"
        directory_crasn._combine_sender_and_receiver_nodes(node)
        assert node.heartbeat != -1
        assert directory_crasn._node_ids[b"n3"] == node

    def test_mismatch(self, directory_crasn: Directory):
        node = Node()
        node.namespace = b"N4"
        directory_crasn._combine_sender_and_receiver_nodes(node)
        assert node.heartbeat == -1
        assert directory_crasn._node_ids[b"n3"] != node


class Test_remove_node_without_checks:
    def test_remove_only_receiver(self, directory: Directory):
        directory.add_node_receiver(b"n3", b"N3")
        assert b"n3" in directory._node_ids
        directory._remove_node_without_checks(b"N3")
        assert b"n3" not in directory._node_ids
        assert b"N3" not in directory._nodes

    def test_remove_complete_node(self, directory: Directory):
        assert b"n2" in directory._node_ids
        assert b"N2" in directory._nodes
        directory._remove_node_without_checks(b"N2")
        assert b"n2" not in directory._node_ids
        assert b"N2" not in directory._nodes

    def test_remove_by_namespace(self, directory: Directory):
        node = Node()
        directory._nodes[b"N3"] = node
        directory._node_ids[b"some_id"] = node
        directory._remove_node_without_checks(b"N3")
        assert b"some_id" not in directory._node_ids
        assert b"N3" not in directory._nodes


class Test_update_heartbeat:
    def test_local_component(self, fake_counting, directory: Directory):
        directory.update_heartbeat(b"send_id", Message.from_frames(b"", b"", b"N1.send", b""))
        assert directory.get_components()[b"send"].heartbeat == 0

    def test_local_component_without_namespace(self, fake_counting, directory: Directory):
        directory.update_heartbeat(b"send_id", Message.from_frames(b"", b"", b"send", b""))
        assert directory.get_components()[b"send"].heartbeat == 0

    def test_local_component_signs_in(self, directory: Directory):
        directory.update_heartbeat(b"new_id", Message.from_frames(
            b"", b"COORDINATOR", b"send2", b"",
            b'{"id": 2, "method": "sign_in", "jsonrpc": "2.0"}'))
        # test that no error is raised

    def test_not_signed_in_component_signs_out(self, directory: Directory):
        # TODO not determined by LECO
        directory.update_heartbeat(b"new_id", Message.from_frames(
            b"", b"COORDINATOR", b"send2", b"",
            b'{"id": 2, "method": "sign_out", "jsonrpc": "2.0"}'))
        # test that no error is raised

    def test_local_component_with_wrong_id(self, directory: Directory):
        with pytest.raises(CommunicationError, match=DUPLICATE_NAME.message):
            directory.update_heartbeat(b"new_id", Message.from_frames(
                b"", b"COORDINATOR", b"send", b""))

    def test_local_component_with_wrong_id_signs_in(self, directory: Directory):
        with pytest.raises(CommunicationError, match=DUPLICATE_NAME.message):
            directory.update_heartbeat(b"new_id", Message(
                receiver=b"COORDINATOR", sender=b"send",
                message_type=MessageTypes.JSON,
                data={"jsonrpc": "2.0", "id": 2, "method": "sign_in"}))

    def test_known_node(self, fake_counting, directory: Directory):
        directory.update_heartbeat(b"n2", Message.from_frames(b"", b"COORDINATOR", b"N2.send", b""))
        assert directory.get_node_ids()[b"n2"].heartbeat == 0

    @pytest.mark.parametrize("data", (
            {"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 7},
            {"jsonrpc": "2.0", "method": "coordinator_sign_out", "id": 7},
    ))
    def test_signing_in_out_node(self, directory: Directory, data):
        directory.update_heartbeat(b"n3", Message(
            b"COORDINATOR", b"N3.COORDINATOR", data=data, message_type=MessageTypes.JSON))
        # test that no error is raised

    def test_from_unknown_node(self, directory: Directory):
        with pytest.raises(CommunicationError, match="not signed in"):
            directory.update_heartbeat(b"n3", Message(b"COORDINATOR", b"N3.send"))


class Test_find_expired_components:
    def test_expired_component(self, directory: Directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -3.5
        directory.find_expired_components(1)
        assert b"send" not in directory.get_components().keys()

    def test_warn_component(self, directory: Directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -1.5
        assert directory.find_expired_components(1) == [(b"send_id", b"send")]

    def test_active_Component(self, directory: Directory, fake_counting):
        directory.get_components()[b"send"].heartbeat = -0.5
        assert directory.find_expired_components(1) == []
        assert b"send" in directory.get_components()


class Test_find_expired_nodes:

    def test_expired_node(self, directory: Directory, fake_counting):
        directory.get_node_ids()[b"n2"].heartbeat = -3.5
        directory.find_expired_nodes(1)
        assert b"n2" not in directory.get_node_ids()

    def test_warn_node(self, directory: Directory, fake_counting, fake_cid_generation):
        directory.get_node_ids()[b"n2"].heartbeat = -1.5
        directory.find_expired_nodes(1)
        assert directory.get_node_ids()[b"n2"]._messages_sent == [  # type: ignore
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR",
                    Request(id=0, method="pong"),
                    message_type=MessageTypes.JSON,
                    conversation_id=cid)]

    def test_active_node(self, directory: Directory, fake_counting):
        directory.get_node_ids()[b"n2"].heartbeat = -0.5
        directory.find_expired_nodes(1)
        assert b"n2" in directory.get_node_ids()

    def test_expired_waiting_node(self, directory: Directory, fake_counting):
        waiting_node = FakeNode()
        waiting_node.heartbeat = - 3.5
        directory._waiting_nodes["address"] = waiting_node
        # act
        directory.find_expired_nodes(1)
        assert "address" not in directory._waiting_nodes


def test_get_node_id(directory: Directory):
    assert directory.get_node_id(b"N2") == b"n2"


def test_get_node_id_not_first_place_in_list(directory: Directory):
    n3 = FakeNode()
    n3.namespace = b"N3"
    directory._node_ids[b"n3"] = n3
    assert directory.get_node_id(b"N3") == b"n3"


def test_get_node_id_fails(directory: Directory):
    with pytest.raises(ValueError, match="No receiving connection to namespace"):
        directory.get_node_id(b"N5")


class Test_sign_out_from_node:
    @pytest.fixture
    def directory_wo_n2(self, fake_cid_generation, directory: Directory) -> Directory:
        directory._test = directory.get_node(b"N2")  # type: ignore
        directory.sign_out_from_node(b"N2")
        return directory

    def test_message_sent(self, directory_wo_n2: Directory):
        assert directory_wo_n2._test._messages_sent == [  # type: ignore
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR",
                    data={"id": 1, "method": "coordinator_sign_out", "jsonrpc": "2.0"},
                    message_type=MessageTypes.JSON,
                    conversation_id=cid)]

    def test_connection_closed(self, directory_wo_n2: Directory):
        assert directory_wo_n2._test.is_connected() is False  # type: ignore

    def test_n2_removed_from_nodes(self, directory_wo_n2: Directory):
        assert b"N2" not in directory_wo_n2.get_nodes()

    def test_n2_removed_from_node_ids(self, directory_wo_n2: Directory):
        assert b"n2" not in directory_wo_n2.get_node_ids()


def test_sign_out_from_unknown_node_fails(directory: Directory):
    with pytest.raises(ValueError, match="is not known"):
        directory.sign_out_from_node(b"unknown node")
