#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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

from unittest.mock import patch

import pytest

from pyleco.coordinators.data_coordinator import DataCoordinator
from pyleco.core import (
    PROXY_RECEIVING_PORT,
    PROXY_SENDING_PORT,
    PROXY_GATHERER_PORT,
    LOG_RECEIVING_PORT,
    LOG_SENDING_PORT,
    LOG_GATHERER_PORT,
)
from pyleco.json_utils.errors import (
    GATHERER_ALREADY_CONNECTED,
    GATHERER_NOT_CONNECTED,
    JSONRPCError,
)
from pyleco.test import FakeContext


@pytest.fixture
def data_coordinator():
    with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"):
        dc = DataCoordinator(
            host="myhost",
            context=FakeContext(),  # type: ignore[reportArgumentType]
            start_listener=False,
        )
        yield dc
        dc.close()


@pytest.fixture
def log_coordinator():
    with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"):
        dc = DataCoordinator(
            name="LOG_COORDINATOR",
            host="myhost",
            context=FakeContext(),  # type: ignore[reportArgumentType]
            xsub_port=11098,
            gatherer_xpub_port=11096,
            xpub_port=11097,
            start_listener=False,
        )
        yield dc
        dc.close()


class TestDataCoordinatorInit:
    def test_name_set(self, data_coordinator: DataCoordinator):
        assert data_coordinator.name == "DATA_COORDINATOR"

    def test_full_name_without_namespace(self, data_coordinator: DataCoordinator):
        assert data_coordinator.full_name == "DATA_COORDINATOR"

    def test_host_set(self, data_coordinator: DataCoordinator):
        assert data_coordinator.host == "myhost"

    def test_data_addresses_uses_host(self, data_coordinator: DataCoordinator):
        addresses = data_coordinator.send_data_addresses()
        assert addresses == {
            "gatherer_xsub": f"myhost:{PROXY_RECEIVING_PORT}",
            "gatherer_xpub": f"myhost:{PROXY_GATHERER_PORT}",
            "distributor_xpub": f"myhost:{PROXY_SENDING_PORT}",
        }

    def test_initial_gatherers_empty(self, data_coordinator: DataCoordinator):
        assert data_coordinator.list_gatherers() == []

    def test_own_context_false_when_passed(self, data_coordinator: DataCoordinator):
        assert data_coordinator._own_context is False

    def test_own_context_true_when_none(self):
        with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"), patch(
            "pyleco.coordinators.data_coordinator.zmq.Context.instance",
            return_value=FakeContext(),
        ):
            dc = DataCoordinator(
                host="localhost",
                context=None,
                start_listener=False,
            )
            assert dc._own_context is True
            dc.close()


class TestLogCoordinatorInit:
    def test_name(self, log_coordinator: DataCoordinator):
        assert log_coordinator.name == "LOG_COORDINATOR"

    def test_data_addresses_uses_host(self, log_coordinator: DataCoordinator):
        addresses = log_coordinator.send_data_addresses()
        assert addresses == {
            "gatherer_xsub": f"myhost:{LOG_RECEIVING_PORT}",
            "gatherer_xpub": f"myhost:{LOG_GATHERER_PORT}",
            "distributor_xpub": f"myhost:{LOG_SENDING_PORT}",
        }


class TestConnectToGatherer:
    def test_connect_adds_address(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        assert "host:11101" in data_coordinator._remote_gatherer_addresses

    def test_connect_returns_none(self, data_coordinator: DataCoordinator):
        result = data_coordinator.connect_to_gatherer("host:11101")
        assert result is None

    def test_connect_duplicate_raises(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        with pytest.raises(JSONRPCError) as exc_info:
            data_coordinator.connect_to_gatherer("host:11101")
        assert exc_info.value.rpc_error.code == GATHERER_ALREADY_CONNECTED.code

    def test_connect_duplicate_error_includes_address(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        with pytest.raises(JSONRPCError) as exc_info:
            data_coordinator.connect_to_gatherer("host:11101")
        assert exc_info.value.rpc_error.data == "host:11101"

    def test_connect_multiple(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host1:11101")
        data_coordinator.connect_to_gatherer("host2:11101")
        assert len(data_coordinator._remote_gatherer_addresses) == 2

    def test_connect_calls_distributor_xsub_connect(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        assert data_coordinator.distributor_xsub.addr == "tcp://host:11101"


class TestDisconnectFromGatherer:
    def test_disconnect_removes_address(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        data_coordinator.disconnect_from_gatherer("host:11101")
        assert "host:11101" not in data_coordinator._remote_gatherer_addresses

    def test_disconnect_returns_none(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        result = data_coordinator.disconnect_from_gatherer("host:11101")
        assert result is None

    def test_disconnect_not_connected_raises(self, data_coordinator: DataCoordinator):
        with pytest.raises(JSONRPCError) as exc_info:
            data_coordinator.disconnect_from_gatherer("host:11101")
        assert exc_info.value.rpc_error.code == GATHERER_NOT_CONNECTED.code

    def test_disconnect_error_includes_address(self, data_coordinator: DataCoordinator):
        with pytest.raises(JSONRPCError) as exc_info:
            data_coordinator.disconnect_from_gatherer("host:11101")
        assert exc_info.value.rpc_error.data == "host:11101"

    def test_disconnect_calls_distributor_xsub_disconnect(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host:11101")
        data_coordinator.disconnect_from_gatherer("host:11101")
        assert data_coordinator.distributor_xsub.addr is None


class TestListGatherers:
    def test_empty(self, data_coordinator: DataCoordinator):
        assert data_coordinator.list_gatherers() == []

    def test_returns_sorted(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host_b:11101")
        data_coordinator.connect_to_gatherer("host_a:11101")
        result = data_coordinator.list_gatherers()
        assert result == ["host_a:11101", "host_b:11101"]

    def test_after_disconnect(self, data_coordinator: DataCoordinator):
        data_coordinator.connect_to_gatherer("host_a:11101")
        data_coordinator.connect_to_gatherer("host_b:11101")
        data_coordinator.disconnect_from_gatherer("host_a:11101")
        assert data_coordinator.list_gatherers() == ["host_b:11101"]


class TestSendDataAddresses:
    def test_returns_dict(self, data_coordinator: DataCoordinator):
        result = data_coordinator.send_data_addresses()
        assert isinstance(result, dict)

    def test_has_required_keys(self, data_coordinator: DataCoordinator):
        result = data_coordinator.send_data_addresses()
        assert "gatherer_xsub" in result
        assert "gatherer_xpub" in result
        assert "distributor_xpub" in result

    def test_uses_host_not_wildcard(self, data_coordinator: DataCoordinator):
        result = data_coordinator.send_data_addresses()
        assert result["gatherer_xsub"] == f"myhost:{PROXY_RECEIVING_PORT}"
        assert result["gatherer_xpub"] == f"myhost:{PROXY_GATHERER_PORT}"
        assert result["distributor_xpub"] == f"myhost:{PROXY_SENDING_PORT}"

    def test_custom_host(self):
        with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"):
            dc = DataCoordinator(
                host="192.168.1.100",
                context=FakeContext(),  # type: ignore[reportArgumentType]
                start_listener=False,
            )
            result = dc.send_data_addresses()
            assert result["gatherer_xsub"] == f"192.168.1.100:{PROXY_RECEIVING_PORT}"
            assert result["gatherer_xpub"] == f"192.168.1.100:{PROXY_GATHERER_PORT}"
            assert result["distributor_xpub"] == f"192.168.1.100:{PROXY_SENDING_PORT}"
            dc.close()


class TestContextManager:
    def test_context_manager_closes(self):
        with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"):
            with DataCoordinator(
                host="localhost",
                context=FakeContext(),  # type: ignore[reportArgumentType]
                start_listener=False,
            ) as dc:
                assert not dc.closed
            assert dc.closed

    def test_close_idempotent(self, data_coordinator: DataCoordinator):
        data_coordinator.close()
        data_coordinator.close()
        assert data_coordinator.closed

    def test_shared_context_not_terminated(self):
        ctx = FakeContext()
        with patch("pyleco.coordinators.data_coordinator.zmq.proxy_steerable"):
            dc = DataCoordinator(
                host="localhost",
                context=ctx,  # type: ignore[reportArgumentType]
                start_listener=False,
            )
        assert dc._own_context is False
        dc.close()
        assert not hasattr(ctx, "closed") or not ctx.closed

    def test_close_on_partial_init_does_not_raise(self):
        dc = DataCoordinator.__new__(DataCoordinator)
        dc.closed = False
        dc._control_sockets = []
        dc._proxy_threads = []
        dc._own_context = False
        dc.close()
        assert dc.closed


class TestComponentMethods:
    def test_shut_down(self, data_coordinator: DataCoordinator):
        data_coordinator.shut_down()
        assert data_coordinator.closed


class TestMainGathererArgs:
    """Test that --data-gatherers and --log-gatherers CLI args connect at startup."""

    @patch("pyleco.coordinators.data_coordinator.zmq.Context")
    @patch("pyleco.coordinators.data_coordinator.DataCoordinator")
    def test_data_gatherers_connected(self, mock_dc_cls, mock_ctx_cls):
        from pyleco.coordinators.data_coordinator import main

        mock_dc_instance = mock_dc_cls.return_value
        with patch(
            "sys.argv",
            ["data_coordinator", "--no-log", "--data-gatherers", "host1:11101,host2:11101"],
        ):
            main()
        calls = [c.args[0] for c in mock_dc_instance.connect_to_gatherer.call_args_list]
        assert calls == ["host1:11101", "host2:11101"]

    @patch("pyleco.coordinators.data_coordinator.zmq.Context")
    @patch("pyleco.coordinators.data_coordinator.DataCoordinator")
    def test_log_gatherers_connected(self, mock_dc_cls, mock_ctx_cls):
        from pyleco.coordinators.data_coordinator import main

        mock_dc_instance = mock_dc_cls.return_value
        with patch(
            "sys.argv", ["data_coordinator", "--log-gatherers", "loghost1:11101, loghost2:11101"]
        ):
            main()
        calls = [c.args[0] for c in mock_dc_instance.connect_to_gatherer.call_args_list]
        assert "loghost1:11101" in calls
        assert "loghost2:11101" in calls

    @patch("pyleco.coordinators.data_coordinator.zmq.Context")
    @patch("pyleco.coordinators.data_coordinator.DataCoordinator")
    def test_no_gatherers_by_default(self, mock_dc_cls, mock_ctx_cls):
        from pyleco.coordinators.data_coordinator import main

        mock_dc_instance = mock_dc_cls.return_value
        with patch("sys.argv", ["data_coordinator", "--no-log"]):
            main()
        mock_dc_instance.connect_to_gatherer.assert_not_called()

    @patch("pyleco.coordinators.data_coordinator.zmq.Context")
    @patch("pyleco.coordinators.data_coordinator.DataCoordinator")
    def test_spaces_stripped_from_gatherers(self, mock_dc_cls, mock_ctx_cls):
        from pyleco.coordinators.data_coordinator import main

        mock_dc_instance = mock_dc_cls.return_value
        with patch(
            "sys.argv",
            ["data_coordinator", "--no-log", "--data-gatherers", " host1:11101 , host2:11101 "],
        ):
            main()
        calls = [c.args[0] for c in mock_dc_instance.connect_to_gatherer.call_args_list]
        assert calls == ["host1:11101", "host2:11101"]
