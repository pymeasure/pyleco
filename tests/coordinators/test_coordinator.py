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
from unittest.mock import MagicMock

import pytest

from pyleco.json_utils.json_objects import Request, ErrorResponse, DataError
from pyleco.json_utils.errors import NODE_UNKNOWN, NOT_SIGNED_IN, DUPLICATE_NAME, RECEIVER_UNKNOWN
from pyleco.core import VERSION_B
from pyleco.core.message import Message, MessageTypes
from pyleco.core.leco_protocols import ExtendedComponentProtocol, Protocol, CoordinatorProtocol
from pyleco.utils.coordinator_utils import FakeMultiSocket, FakeNode
from pyleco.json_utils.rpc_generator import RPCGenerator
from pyleco.test import FakeContext
from pyleco.utils.events import SimpleEvent

from pyleco.coordinators.coordinator import Coordinator
from pyleco.coordinators import coordinator as coordinator_module  # type: ignore


@pytest.fixture
def coordinator() -> Coordinator:
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
    coordinator.sock._messages_sent = []  # type: ignore  # reset router sock._socket:
    return coordinator


def fake_perf_counter() -> float:
    return 0.


@pytest.fixture()
def fake_counting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyleco.utils.coordinator_utils.perf_counter", fake_perf_counter)


cid = b"conversation_id;"


def fake_generate_cid() -> bytes:
    return cid


@pytest.fixture(autouse=True)
def fake_cid_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pyleco.core.serialization.generate_conversation_id", fake_generate_cid)


class ExtendedCoordinator(CoordinatorProtocol, ExtendedComponentProtocol, Protocol):
    pass


class TestCoordinatorImplementsProtocol:
    protocol_methods = [m for m in dir(ExtendedCoordinator) if not m.startswith("_")]

    def static_test_methods_are_present(self):
        def testing(component: ExtendedCoordinator):
            pass
        testing(Coordinator())

    @pytest.fixture
    def component_methods(self, coordinator: Coordinator):
        response = coordinator.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}')
        result = RPCGenerator().get_result_from_response(response)  # type: ignore
        return result.get('methods')

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(self, component_methods, method):
        for m in component_methods:
            if m.get('name') == method:
                return
        raise AssertionError(f"Method {method} is not available.")


class Test_coordinator_set_namespace_from_hostname:
    @pytest.fixture
    def namespace(self) -> bytes:
        coordinator = Coordinator(context=FakeContext())  # type: ignore
        return coordinator.namespace

    def test_namespace_is_bytes(self, namespace):
        assert isinstance(namespace, bytes)

    def test_namespace_without_periods(self, namespace):
        assert b"." not in namespace

    def test_namespace_from_hostname_with_periods(self, monkeypatch: pytest.MonkeyPatch):
        def fake_gethostname() -> str:
            return "hostname.domain.tld"
        monkeypatch.setattr(coordinator_module, "gethostname", fake_gethostname)
        coordinator = Coordinator(context=FakeContext())  # type: ignore
        assert coordinator.namespace == b"hostname"


def test_coordinator_set_namespace_bytes():
    coordinator = Coordinator(namespace=b"test", context=FakeContext())  # type: ignore
    assert coordinator.namespace == b"test"


def test_coordinator_set_namespace_invalid():
    with pytest.raises(ValueError, match="namespace"):
        Coordinator(namespace=1234, context=FakeContext())  # type: ignore


def test_set_address_from_hostname():
    coordinator = Coordinator(context=FakeContext())  # type: ignore
    assert isinstance(coordinator.address, str)


def test_set_address_manually():
    host = "host"
    coordinator = Coordinator(host=host, context=FakeContext())  # type: ignore
    assert coordinator.address == f"{host}:12300"


class TestClose:
    @pytest.fixture
    def coordinator_closed(self, coordinator: Coordinator):
        coordinator.shut_down = MagicMock()  # type: ignore[method-assign]
        coordinator.close()
        return coordinator

    def test_call_shutdown(self, coordinator_closed: Coordinator):
        coordinator_closed.shut_down.assert_called_once()  # type: ignore

    def test_close_socket(self, coordinator_closed: Coordinator):
        assert coordinator_closed.sock.closed is True


def test_context_manager_calls_close():
    with Coordinator(multi_socket=FakeMultiSocket()) as c:
        c.close = MagicMock()  # type: ignore[method-assign]
    c.close.assert_called_once()


class Test_clean_addresses:
    def test_expired_component(self, coordinator: Coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -3.5
        coordinator.remove_expired_addresses(1)
        assert b"send" not in coordinator.directory.get_component_names()

    def test_expired_component_updates_directory(self, coordinator: Coordinator, fake_counting):
        coordinator.publish_directory_update = MagicMock()  # type: ignore
        coordinator.directory.get_components()[b"send"].heartbeat = -3.5
        coordinator.remove_expired_addresses(1)
        coordinator.publish_directory_update.assert_called()

    def test_warn_component(self, coordinator: Coordinator, fake_counting):
        # TODO implement heartbeat request
        coordinator.directory.get_components()[b"send"].heartbeat = -1.5
        coordinator.remove_expired_addresses(1)
        assert coordinator.sock._messages_sent == [(b"321", Message(  # type: ignore
            b"N1.send", b"N1.COORDINATOR",
            message_type=MessageTypes.JSON,
            data=Request(id=0, method="pong")))]

    def test_active_Component_remains_in_directory(self, coordinator: Coordinator, fake_counting):
        coordinator.directory.get_components()[b"send"].heartbeat = -0.5
        coordinator.remove_expired_addresses(1)
        assert coordinator.sock._messages_sent == []  # type: ignore
        assert b"send" in coordinator.directory.get_components()

    def test_expired_Coordinator(self, coordinator: Coordinator, fake_counting):
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -3.5
        coordinator.remove_expired_addresses(1)
        assert b"n2" not in coordinator.directory.get_node_ids()
        # further removal tests in :class:`Test_remove_coordinator`

    def test_warn_Coordinator(self, coordinator: Coordinator, fake_counting):
        coordinator.publish_directory_update = MagicMock()  # type: ignore
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -1.5
        coordinator.remove_expired_addresses(1)
        assert coordinator.directory.get_node_ids()[b"n2"]._messages_sent == [  # type: ignore
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data=Request(id=0, method="pong")),
        ]

    def test_active_Coordinator_remains_in_directory(self, coordinator: Coordinator, fake_counting):
        coordinator.directory.get_node_ids()[b"n2"].heartbeat = -0.5
        coordinator.remove_expired_addresses(1)
        assert b"n2" in coordinator.directory.get_node_ids()


def test_heartbeat_local(fake_counting, coordinator: Coordinator):
    coordinator.sock._messages_read = [  # type: ignore
        [b"321", Message(b"COORDINATOR", b"send")]]
    coordinator.read_and_route()
    assert coordinator.directory.get_components()[b"send"].heartbeat == 0


def test_routing_connects_to_coordinators(coordinator: Coordinator):
    event = SimpleEvent()
    event.set()
    coordinator.directory.add_node_sender = MagicMock()  # type: ignore
    coordinator.routing(["abc"], stop_event=event)
    coordinator.directory.add_node_sender.assert_called_once


@pytest.mark.parametrize("i, o", (
    ([b"321", VERSION_B, b"COORDINATOR", b"send", b";", b""], None),  # test heartbeat alone
    ([b"321", VERSION_B, b"rec", b"send", b";", b"1"],
     [b"123", VERSION_B, b"rec", b"send", b";", b"1"]),  # receiver known, sender known.
))
def test_routing_successful(coordinator: Coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: successful routing."""
    coordinator.sock._messages_read = [  # type: ignore
        (i[0], Message.from_frames(*i[1:]))]
    coordinator.read_and_route()
    if o is None:
        assert coordinator.sock._messages_sent == []  # type: ignore
    else:
        assert coordinator.sock._messages_sent == [  # type: ignore
            (o[0], Message.from_frames(*o[1:]))]


def test_reading_fails(coordinator: Coordinator, caplog: pytest.LogCaptureFixture):
    def read_message() -> tuple[bytes, Message]:
        return b"", Message.from_frames(*[b"frame 1", b"frame 2"])  # less frames than needed.
    coordinator.sock.read_message = read_message  # type: ignore
    coordinator.read_and_route()
    assert caplog.records[-1].msg == "Not enough frames read."


@pytest.mark.parametrize("i, o", (
    # receiver unknown, return to sender:
    ([b"321", VERSION_B, b"x", b"send", b"conversation_id;mid0", b""],
     [b"321", VERSION_B, b"send", b"N1.COORDINATOR", b"conversation_id;\x00\x00\x00\x01",
      ErrorResponse(id=None,
                    error=DataError.from_error(RECEIVER_UNKNOWN,
                                               "x")).model_dump_json().encode()]),
    # unknown receiver node:
    ([b"321", VERSION_B, b"N3.CB", b"N1.send", b"conversation_id;mid0"],
     [b"321", VERSION_B, b"N1.send", b"N1.COORDINATOR", b"conversation_id;\x00\x00\x00\x01",
      ErrorResponse(id=None,
                    error=DataError.from_error(NODE_UNKNOWN,
                                               "N3")).model_dump_json().encode()]),
    # sender (without namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"unknownSender", b"conversation_id;mid0"],
     [b"1", VERSION_B, b"unknownSender", b"N1.COORDINATOR", b"conversation_id;\x00\x00\x00\x01",
      ErrorResponse(id=None, error=NOT_SIGNED_IN).model_dump_json().encode()]),
    # sender (with given Namespace) did not sign in:
    ([b"1", VERSION_B, b"rec", b"N1.unknownSender", b"conversation_id;mid0"],
     [b"1", VERSION_B, b"N1.unknownSender", b"N1.COORDINATOR", b"conversation_id;\x00\x00\x00\x01",
      ErrorResponse(id=None, error=NOT_SIGNED_IN).model_dump_json().encode()]),
    # unknown sender with a rogue node name:
    ([b"1", VERSION_B, b"rec", b"N2.unknownSender", b"conversation_id;mid0"],
     [b"1", VERSION_B, b"N2.unknownSender", b"N1.COORDINATOR", b"conversation_id;\x00\x00\x00\x01",
      ErrorResponse(id=None, error=NOT_SIGNED_IN).model_dump_json().encode()]),
))
def test_routing_error_messages(coordinator: Coordinator, i, o):
    """Test whether some incoming message `i` is sent as `o`. Here: Error messages."""
    coordinator.sock._messages_read = [  # type: ignore
        (i[0], Message.from_frames(*i[1:]))]
    coordinator.read_and_route()
    if o is None:
        assert coordinator.sock._messages_sent == []  # type: ignore
    else:
        assert coordinator.sock._messages_sent == [  # type: ignore
            (o[0], Message.from_frames(*o[1:]))]


def test_remote_routing(coordinator: Coordinator):
    coordinator.sock._messages_read = [  # type: ignore
        [b"321", Message(b"N2.CB", b"N1.send")]]
    coordinator.read_and_route()
    assert coordinator.directory.get_node(b"N2")._messages_sent == [  # type: ignore
        Message(b"N2.CB", b"N1.send")]


@pytest.mark.parametrize("sender", (b"N2.CB", b"N2.COORDINATOR"))
def test_remote_heartbeat(coordinator: Coordinator, fake_counting, sender):
    coordinator.sock._messages_read = [  # type: ignore
        [b"n2", Message(b"N3.CA", sender)]]
    assert coordinator.directory.get_node_ids()[b"n2"].heartbeat != 0
    coordinator.read_and_route()
    assert coordinator.directory.get_node_ids()[b"n2"].heartbeat == 0


class Test_handle_commands:
    class SpecialCoordinator(Coordinator):
        def handle_rpc_call(self, message: Message) -> None:
            self._rpc = message

    @pytest.fixture
    def coordinator_hc(self) -> Coordinator:
        return self.SpecialCoordinator(
            namespace="N1", host="N1host", cleaning_interval=1e5,
            context=FakeContext(),  # type: ignore
            multi_socket=FakeMultiSocket())

    def test_store_message(self, coordinator_hc: Coordinator):
        msg = Message(b"receiver", b"sender", header=b"header", data=b"data")
        coordinator_hc.handle_commands(b"identity", msg)
        assert coordinator_hc.current_message == msg

    def test_store_identity(self, coordinator_hc: Coordinator):
        msg = Message(b"receiver", b"sender", header=b"header", data=b"data")
        coordinator_hc.handle_commands(b"identity", msg)
        assert coordinator_hc.current_identity == b"identity"

    @pytest.mark.parametrize("identity, message", (
        (b"3", Message(b"", message_type=MessageTypes.JSON,
                       data={"jsonrpc": "2.0", "method": "some"})),
    ))
    def test_call_handle_rpc_call(self, coordinator_hc: Coordinator, identity, message):
        coordinator_hc.handle_commands(identity, message)
        assert coordinator_hc._rpc == message  # type: ignore

    def test_log_error_response(self, coordinator_hc: Coordinator):
        pass  # TODO

    def test_pass_at_null_result(self, coordinator_hc: Coordinator):
        coordinator_hc.handle_commands(b"",
                                       Message(b"",
                                               message_type=MessageTypes.JSON,
                                               data={"jsonrpc": "2.0", "result": None}))
        assert not hasattr(coordinator_hc, "_rpc")
        # assert no error log entry.  TODO

    def test_log_at_non_null_result(self, coordinator_hc: Coordinator,
                                    caplog: pytest.LogCaptureFixture):
        caplog.set_level(10)
        coordinator_hc.handle_commands(b"",
                                       Message(b"",
                                               message_type=MessageTypes.JSON,
                                               data={"jsonrpc": "2.0", "result": 5}))
        assert not hasattr(coordinator_hc, "_rpc")
        # assert no error log entry.  TODO
        caplog.records[-1].msg.startswith("Unexpected result")

    def test_pass_at_batch_of_null_results(self, coordinator_hc: Coordinator):
        coordinator_hc.handle_commands(b"",
                                       Message(b"",
                                               message_type=MessageTypes.JSON,
                                               data=[{"jsonrpc": "2.0", "result": None, "id": 1},
                                                     {"jsonrpc": "2.0", "result": None, "id": 2}]
                                               ))
        assert not hasattr(coordinator_hc, "_rpc")
        # assert no error log entry.  TODO

    def test_log_at_batch_of_non_null_results(self, coordinator_hc: Coordinator,
                                              caplog: pytest.LogCaptureFixture):
        caplog.set_level(10)
        coordinator_hc.handle_commands(b"",
                                       Message(b"",
                                               message_type=MessageTypes.JSON,
                                               data=[{"jsonrpc": "2.0", "result": None, "id": 1},
                                                     {"jsonrpc": "2.0", "result": 5, "id": 2}]
                                               ))
        assert not hasattr(coordinator_hc, "_rpc")
        caplog.records[-1].msg.startswith("Unexpected result")

    @pytest.mark.parametrize("data", (
            {"jsonrpc": "2.0", "no method": 7},
            ["jsonrpc", "2.0", "no method", 7],  # not a dict
    ))
    def test_invalid_json_does_not_raise_exception(self, coordinator_hc: Coordinator, data):
        coordinator_hc.handle_commands(b"",
                                       Message(receiver=b"COORDINATOR", sender=b"send",
                                               data=data, message_type=MessageTypes.JSON,))
        # assert that no error is raised

    def test_invalid_json_message_raises_log(self, coordinator_hc: Coordinator,
                                             caplog: pytest.LogCaptureFixture):
        data = "funny stuff"
        coordinator_hc.handle_commands(b"",
                                       Message(receiver=b"COORDINATOR", sender=b"send",
                                               data=data, message_type=MessageTypes.JSON,))
        assert caplog.records[-1].msg.startswith("Invalid JSON message")


class Test_sign_in:
    def test_signin(self, coordinator: Coordinator):
        coordinator.sock._messages_read = [  # type: ignore
            [b'cb', Message(b"COORDINATOR", b"CB",
                            data=Request(id=7, method="sign_in"),
                            message_type=MessageTypes.JSON,
                            conversation_id=cid,
                            )]]
        # read_and_route needs to start at routing, to check that the messages passes the heartbeats
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [  # type: ignore
            (b"cb", Message(b"CB", b"N1.COORDINATOR",
                            conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"id": 7, "result": None, "jsonrpc": "2.0"}))]

    def test_signin_sends_directory_update(self, coordinator: Coordinator):
        coordinator.publish_directory_update = MagicMock()  # type: ignore
        coordinator.sock._messages_read = [  # type: ignore
            [b'cb', Message(b"COORDINATOR", b"CB", conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"jsonrpc": "2.0", "method": "sign_in", "id": 7},
                            )]]
        # read_and_route needs to start at routing, to check that the messages passes the heartbeats
        coordinator.read_and_route()
        coordinator.publish_directory_update.assert_any_call()

    def test_signin_rejected(self, coordinator: Coordinator):
        coordinator.sock._messages_read = [  # type: ignore
            [b'cb', Message(b"COORDINATOR", b"send", conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"id": 8, "method": "sign_in", "jsonrpc": "2.0"},
                            )]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"cb", Message(  # type: ignore
            b"send", b"N1.COORDINATOR",
            conversation_id=cid,
            message_type=MessageTypes.JSON,
            data={"id": None, "error": {"code": DUPLICATE_NAME.code,
                                        "message": DUPLICATE_NAME.message},
                  "jsonrpc": "2.0"}
        ))]


class Test_sign_out_successful:
    @pytest.fixture
    def coordinator_signed_out(self, coordinator: Coordinator):
        sign_out_message = Message(receiver=b"N1.COORDINATOR", sender=b"rec",
                                   message_type=MessageTypes.JSON,
                                   data={"jsonrpc": "2.0", "method": "sign_out", "id": 10})
        coordinator.publish_directory_update = MagicMock()  # type: ignore
        coordinator.sock._messages_read = [[b"123", sign_out_message]]  # type: ignore
        coordinator.read_and_route()
        return coordinator

    def test_address_cleared(self, coordinator_signed_out: Coordinator):
        assert b"rec" not in coordinator_signed_out.directory.get_components().keys()

    def test_acknowledgement_sent(self, coordinator_signed_out: Coordinator):
        assert coordinator_signed_out.sock._messages_sent == [  # type: ignore
            (b"123", Message(b"rec", b"N1.COORDINATOR",
                             message_type=MessageTypes.JSON,
                             data={"id": 10, "result": None, "jsonrpc": "2.0"}))]

    def test_directory_update_sent(self, coordinator_signed_out: Coordinator):
        coordinator_signed_out.publish_directory_update.assert_any_call()  # type: ignore

    def test_requires_new_sign_in(self, coordinator_signed_out):
        coordinator = coordinator_signed_out
        coordinator.sock._messages_sent = []  # type: ignore
        coordinator.sock._messages_read = [[b'123', Message(  # type: ignore
            b"N1.COORDINATOR", b"rec",
            message_type=MessageTypes.JSON,
            data={"jsonrpc": "2.0", "result": None, "id": 11})]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"123", Message(  # type: ignore
            b"rec", b"N1.COORDINATOR", message_type=MessageTypes.JSON,
            data=ErrorResponse(id=None, error=NOT_SIGNED_IN)))]


def test_sign_out_clears_address_explicit_namespace(coordinator: Coordinator):
    coordinator.sock._messages_read = [[b'123', Message(  # type: ignore
        b"N1.COORDINATOR", b"N1.rec", message_type=MessageTypes.JSON,
        data={"jsonrpc": "2.0", "method": "sign_out", "id": 10})]]
    coordinator.read_and_route()
    assert b"rec" not in coordinator.directory.get_components().keys()
    assert coordinator.sock._messages_sent == [  # type: ignore
        (b"123", Message(b"N1.rec", b"N1.COORDINATOR", message_type=MessageTypes.JSON,
                         data={"id": 10, "result": None, "jsonrpc": "2.0"}))]


def test_sign_out_of_not_signed_in_generates_acknowledgment_nonetheless(coordinator: Coordinator):
    coordinator.sock._messages_read = [[b'584', Message(  # type: ignore
        b"N1.COORDINATOR", b"rec584", message_type=MessageTypes.JSON,
        data={"jsonrpc": "2.0", "method": "sign_out", "id": 10})]]
    coordinator.read_and_route()
    assert coordinator.sock._messages_sent == [  # type: ignore
        (b"584", Message(b"rec584", b"N1.COORDINATOR", message_type=MessageTypes.JSON,
                         data={"id": 10, "result": None, "jsonrpc": "2.0"}))]


class Test_coordinator_sign_in:
    def test_co_signin_unknown_coordinator_successful(self, coordinator: Coordinator):
        """Test that an unknown Coordinator may sign in."""
        coordinator.sock._messages_read = [  # type: ignore
            [b'n3', Message(b"COORDINATOR", b"N3.COORDINATOR",
                            message_type=MessageTypes.JSON,
                            data={"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 15},
                            conversation_id=cid)]]
        coordinator.read_and_route()
        assert b'n3' in coordinator.directory.get_node_ids().keys()
        assert coordinator.sock._messages_sent == [  # type: ignore
            (b'n3', Message(b"COORDINATOR", b"N1.COORDINATOR",
                            message_type=MessageTypes.JSON,
                            conversation_id=cid, data={"id": 15, "result": None,
                                                       "jsonrpc": "2.0"}))]

    def test_co_signin_known_coordinator_successful(self, fake_counting, coordinator: Coordinator):
        """Test that a Coordinator may sign in as a response to N1's sign in."""

        coordinator.directory.add_node_sender(FakeNode(), "N3host:12345", namespace=b"N3")
        coordinator.directory.get_nodes()[b"N3"] = coordinator.directory._waiting_nodes.pop(
            "N3host:12345")
        coordinator.directory.get_nodes()[b"N3"].namespace = b"N3"

        coordinator.sock._messages_read = [  # type: ignore
            [b'n3', Message(b"COORDINATOR", b"N3.COORDINATOR",
                            conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 15},)]]
        coordinator.read_and_route()
        assert b'n3' in coordinator.directory.get_node_ids().keys()
        assert coordinator.sock._messages_sent == [(b'n3', Message(  # type: ignore
            b"COORDINATOR", b"N1.COORDINATOR", message_type=MessageTypes.JSON, conversation_id=cid,
            data={"id": 15, "result": None, "jsonrpc": "2.0"}))]

    @pytest.mark.xfail(True, reason="Additional error data is added")
    def test_co_signin_rejected(self, coordinator: Coordinator):
        """Coordinator sign in rejected due to already connected Coordinator."""
        coordinator.sock._messages_read = [  # type: ignore
            [b'n3', Message(b"COORDINATOR", b"N2.COORDINATOR",
                            data={"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 15},
                            message_type=MessageTypes.JSON,
                            conversation_id=cid)]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [(b"n3", Message(  # type: ignore
            b"COORDINATOR", b"N1.COORDINATOR",
            data={"id": 15, "error": {"code": -32000, "message": "Server error",
                                      "data": "ValueError: Another Coordinator is known!"},
                  "jsonrpc": "2.0"},
            message_type=MessageTypes.JSON,
            conversation_id=cid))]

    def test_coordinator_sign_in_fails_at_duplicate_name(self, coordinator: Coordinator):
        coordinator.current_message = Message(
            b"COORDINATOR", b"N2.COORDINATOR",
            data={"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 15},
            message_type=MessageTypes.JSON,
            conversation_id=cid)
        coordinator.current_identity = b"n3"
        with pytest.raises(ValueError, match="Another Coordinator is known!"):
            coordinator.coordinator_sign_in()

    def test_co_signin_of_self_rejected(self, coordinator: Coordinator):
        """Coordinator sign in rejected because it is the same coordinator."""
        coordinator.sock._messages_read = [  # type: ignore
            [b'n3', Message(b"COORDINATOR", b"N1.COORDINATOR", conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"jsonrpc": "2.0", "method": "coordinator_sign_in", "id": 15})]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [  # type: ignore
            (b'n3', Message(b"N1.COORDINATOR", b"N1.COORDINATOR", conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data=ErrorResponse(id=None, error=NOT_SIGNED_IN)))]


class Test_coordinator_sign_out:
    def test_co_signout_successful(self, coordinator: Coordinator):
        coordinator.sock._messages_read = [  # type: ignore
            [b'n2', Message(b"COORDINATOR", b"N2.COORDINATOR",
                            conversation_id=cid,
                            message_type=MessageTypes.JSON,
                            data={"id": 10, "method": "coordinator_sign_out", "jsonrpc": "2.0"})]]
        node = coordinator.directory.get_node(b"N2")
        coordinator.read_and_route()
        assert b"n2" not in coordinator.directory.get_node_ids()
        assert node._messages_sent == [Message(  # type: ignore
            b"N2.COORDINATOR", b"N1.COORDINATOR", conversation_id=cid,
            message_type=MessageTypes.JSON,
            data={"id": 100, "method": "coordinator_sign_out", "jsonrpc": "2.0"})]

    @pytest.mark.xfail(True, reason="Not yet defined.")
    def test_co_signout_rejected_due_to_different_identity(self, coordinator: Coordinator):
        """TODO TBD how to handle it"""
        coordinator.set_log_level("DEBUG")
        coordinator.sock._messages_read = [  # type: ignore
            [b'n4', Message(
                receiver=b"COORDINATOR", sender=b"N2.COORDINATOR", conversation_id=cid,
                message_type=MessageTypes.JSON,
                data={"id": 10, "method": "coordinator_sign_out", "jsonrpc": "2.0"})]]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == [  # type: ignore
            (b"n4", Message(
                receiver=b"N2.COORDINATOR", sender=b"N1.COORDINATOR", conversation_id=cid,
                message_type=MessageTypes.JSON,
                data=ErrorResponse(id=None, error=NOT_SIGNED_IN)))]

    def test_co_signout_of_not_signed_in_coordinator(self, coordinator: Coordinator):
        """TODO TBD whether to reject or to ignore."""
        coordinator.sock._messages_read = [  # type: ignore
            (b"n4", Message(b"COORDINATOR", b"N4.COORDINATOR",
                            message_type=MessageTypes.JSON,
                            data={"id": 10, "method": "coordinator_sign_out", "jsonrpc": "2.0"}))]
        coordinator.read_and_route()
        assert coordinator.sock._messages_sent == []  # type: ignore


class Test_shutdown:
    @pytest.fixture
    def shutdown_coordinator(self, coordinator: Coordinator) -> Coordinator:
        self.n2 = coordinator.directory.get_node(b"N2")
        coordinator.stop_event = SimpleEvent()
        coordinator.shut_down()
        return coordinator

    def test_sign_out_message_to_other_coordinators_sent(self, shutdown_coordinator: Coordinator):
        assert self.n2._messages_sent == [  # type: ignore
            Message(b"N2.COORDINATOR", b"N1.COORDINATOR",
                    message_type=MessageTypes.JSON,
                    data={"id": 2, "method": "coordinator_sign_out", "jsonrpc": "2.0"})]

    def test_event_set(self, shutdown_coordinator: Coordinator):
        assert shutdown_coordinator.stop_event.is_set() is True


def test_send_nodes(coordinator: Coordinator):
    data = coordinator.send_nodes()
    assert data == {"N1": "N1host:12300", "N2": "N2host:12300"}


def test_send_local_components(coordinator: Coordinator):
    data = coordinator.send_local_components()
    assert data == ["send", "rec"]


def test_send_global_components(coordinator: Coordinator):
    # Arrange
    coordinator.global_directory[b"N5"] = ["some", "coordinator"]
    # Act
    data = coordinator.send_global_components()
    assert data == {
                 "N5": ["some", "coordinator"],
                 "N1": ["send", "rec"]}


class Test_add_nodes:
    def test_add_nodes(self, coordinator: Coordinator, fake_counting):
        coordinator.add_nodes({"N1": "N1host:12300", "N2": "wrong_host:-7", "N3": "N3host:12300"})
        assert coordinator.directory.get_node(b"N2").address == "N2host:12300"  # not changed
        assert "N3host:12300" in coordinator.directory._waiting_nodes.keys()  # newly created


class Test_record_components:
    def test_set(self, coordinator: Coordinator):
        coordinator.current_message = Message(b"", sender="N2.COORDINATOR")
        coordinator.record_components(["send", "rec"])
        assert coordinator.global_directory == {b"N2": ["send", "rec"]}


def test_publish_directory_updates(coordinator: Coordinator):
    # TODO TBD in LECO
    coordinator.publish_directory_update()
    assert coordinator.directory.get_node_ids()[b"n2"]._messages_sent == [  # type: ignore
        Message(
            b'N2.COORDINATOR', b'N1.COORDINATOR',
            message_type=MessageTypes.JSON,
            data=[
                {"id": 5, "method": "add_nodes",
                    "params": {"nodes": {"N1": "N1host:12300", "N2": "N2host:12300"}},
                    "jsonrpc": "2.0"},
                {"id": 6, "method": "record_components",
                    "params": {"components": ["send", "rec"]},
                    "jsonrpc": "2.0"}]
        ),
    ]
