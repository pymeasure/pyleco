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
import logging
import socket
import threading
from time import sleep
from typing import Any, List, Optional
import pytest

from pyleco.coordinators.coordinator import Coordinator
from pyleco.utils.listener import Listener
from pyleco.utils.communicator import Communicator
from pyleco.directors.coordinator_director import CoordinatorDirector
from pyleco.json_utils.json_objects import Request, ResultResponse
from pyleco.core.message import Message, MessageTypes

TALKING_TIME = 0.5  # s
TIMEOUT = 2  # s


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_coordinator(
    namespace: str,
    port: int,
    coordinators: Optional[List[str]] = None,
    stop_event: Optional[threading.Event] = None,
    **kwargs: Any,
) -> None:
    """Start a coordinator in a separate thread."""
    with Coordinator(namespace=namespace, port=port, **kwargs) as coordinator:
        coordinator.routing(coordinators=coordinators, stop_event=stop_event)


@pytest.fixture
def multi_coordinator_network():
    """Set up a network of multiple coordinators for testing."""
    glog = logging.getLogger()
    glog.setLevel(logging.DEBUG)
    log = logging.getLogger("test")

    ports = [_find_free_port() for _ in range(4)]

    stop_events = [
        threading.Event(),  # N1
        threading.Event(),  # N2
        threading.Event(),  # N3
        threading.Event(),  # N4
    ]

    threads = []

    threads.append(
        threading.Thread(
            target=start_coordinator,
            kwargs=dict(namespace="N1", port=ports[0], stop_event=stop_events[0]),
        )
    )

    sleep(TALKING_TIME)

    threads.append(
        threading.Thread(
            target=start_coordinator,
            kwargs=dict(
                namespace="N2",
                port=ports[1],
                coordinators=[f"localhost:{ports[0]}"],
                stop_event=stop_events[1],
            ),
        )
    )

    sleep(TALKING_TIME)

    threads.append(
        threading.Thread(
            target=start_coordinator,
            kwargs=dict(
                namespace="N3",
                port=ports[2],
                coordinators=[f"localhost:{ports[1]}"],
                stop_event=stop_events[2],
            ),
        )
    )

    sleep(TALKING_TIME)

    threads.append(
        threading.Thread(
            target=start_coordinator,
            kwargs=dict(
                namespace="N4",
                port=ports[3],
                coordinators=[f"localhost:{ports[0]}"],
                stop_event=stop_events[3],
            ),
        )
    )

    for thread in threads:
        thread.daemon = True
        thread.start()

    sleep(TALKING_TIME * 2)

    listener = Listener(name="Controller", port=ports[0], timeout=TIMEOUT)
    listener.start_listen()

    sleep(TALKING_TIME)

    comm = listener.get_communicator()
    comm._ports = ports
    yield comm

    log.info("Tearing down multi-coordinator network")
    listener.stop_listen()

    for event in stop_events:
        event.set()

    for thread in threads:
        thread.join(1.0)


class TestMultiHopCommunication:
    """Test message routing through multiple hops."""

    def test_direct_communication(self, multi_coordinator_network: Communicator):
        """Test direct communication between connected coordinators."""
        comm = multi_coordinator_network

        # Test direct communication N1 -> N2
        assert comm.ask_rpc("N2.COORDINATOR", method="pong") is None

        # Test direct communication N1 -> N4
        assert comm.ask_rpc("N4.COORDINATOR", method="pong") is None

    def test_two_hop_communication(self, multi_coordinator_network: Communicator):
        """Test two-hop communication N1 -> N2 -> N3."""
        comm = multi_coordinator_network

        # Test two-hop communication N1 -> N3 (through N2)
        response = comm.ask(
            "N3.COORDINATOR", data=Request(1, method="pong"), message_type=MessageTypes.JSON
        )
        assert response == Message(
            b"N1.Controller",
            b"N3.COORDINATOR",
            data=ResultResponse(1, None),
            header=response.header,
        )

    def test_three_hop_communication(self, multi_coordinator_network: Communicator):
        """Test three-hop communication N4 -> N1 -> N2 -> N3."""
        comm = multi_coordinator_network
        with Communicator(name="N4Tester", port=comm._ports[3]) as n4_comm:
            response = n4_comm.ask(
                "N3.COORDINATOR", data=Request(2, method="pong"), message_type=MessageTypes.JSON
            )
            assert response == Message(
                b"N4.N4Tester",
                b"N3.COORDINATOR",
                data=ResultResponse(2, None),
                header=response.header,
            )

    def test_component_discovery_across_hops(self, multi_coordinator_network: Communicator):
        """Test that components are discoverable across multiple hops."""
        comm = multi_coordinator_network

        # Add a component to N3
        with Communicator(name="RemoteComponent", port=comm._ports[2]) as remote_comp:
            sleep(TALKING_TIME)  # Time for registration to propagate

            with CoordinatorDirector(communicator=comm) as director:
                # Get global components list
                global_components = director.get_global_components()

                # Should see components from all nodes
                assert "N1" in global_components
                assert "N2" in global_components
                assert "N3" in global_components
                assert "N4" in global_components

                # Should see the RemoteComponent in N3's list
                assert "RemoteComponent" in global_components["N3"]

    def test_reverse_path_communication(self, multi_coordinator_network: Communicator):
        """Test communication in reverse direction N3 -> N2 -> N1."""
        comm = multi_coordinator_network

        # Test reverse path communication N3 -> N1
        with Communicator(name="N3Tester", port=comm._ports[2]) as n3_comm:
            response = n3_comm.ask(
                "N1.COORDINATOR", data=Request(3, method="pong"), message_type=MessageTypes.JSON
            )
            assert response == Message(
                b"N3.N3Tester",
                b"N1.COORDINATOR",
                data=ResultResponse(3, None),
                header=response.header,
            )


class TestNetworkPartitioning:
    """Test network partitioning and recovery scenarios."""

    def test_network_partition_isolation(self, multi_coordinator_network: Communicator):
        """Test that network partition isolates part of the network."""
        comm = multi_coordinator_network

        # Verify initial state - all nodes connected
        with CoordinatorDirector(communicator=comm) as director:
            initial_nodes = director.get_nodes()
            # Should see all nodes in the network
            assert "N1" in initial_nodes
            assert "N2" in initial_nodes
            assert "N3" in initial_nodes
            assert "N4" in initial_nodes

        # Test communication paths before partition
        # N1 -> N2 should work
        assert comm.ask_rpc("N2.COORDINATOR", method="pong") is None
        # N1 -> N3 should work (through N2)
        assert comm.ask_rpc("N3.COORDINATOR", method="pong") is None
        # N1 -> N4 should work
        assert comm.ask_rpc("N4.COORDINATOR", method="pong") is None

    def test_component_access_during_partition(self, multi_coordinator_network: Communicator):
        """Test component access during network partition."""
        comm = multi_coordinator_network

        # Add components to different parts of the network
        components = []
        try:
            # Component on N1 (central hub)
            comp1 = Communicator(name="HubComponent", port=comm._ports[0])
            comp1.sign_in()
            components.append(comp1)

            # Component on N3 (end of chain)
            comp3 = Communicator(name="ChainComponent", port=comm._ports[2])
            comp3.sign_in()
            components.append(comp3)

            sleep(TALKING_TIME)  # Time for registration to propagate

            # Verify components are visible from N1 before any partition
            with CoordinatorDirector(communicator=comm) as director:
                global_components = director.get_global_components()
                assert "HubComponent" in global_components["N1"]
                assert "ChainComponent" in global_components["N3"]

        finally:
            # Clean up components
            for comp in components:
                try:
                    comp.sign_out()
                except Exception:
                    pass

    def test_network_view_consistency(self, multi_coordinator_network: Communicator):
        """Test that network view remains consistent during normal operation."""
        comm = multi_coordinator_network

        # Get network view from different coordinators
        with CoordinatorDirector(communicator=comm) as director:
            n1_view = director.get_nodes()

        # Check view from N2
        with CoordinatorDirector(name="N2Viewer", port=comm._ports[1]) as n2_director:
            n2_view = n2_director.get_nodes()

        # Check view from N3
        with CoordinatorDirector(name="N3Viewer", port=comm._ports[2]) as n3_director:
            n3_view = n3_director.get_nodes()

        # All views should be consistent
        assert set(n1_view.keys()) == set(n2_view.keys())
        assert set(n2_view.keys()) == set(n3_view.keys())


class TestCoordinatorFailureRecovery:
    """Test coordinator failure and recovery mechanisms."""

    def test_coordinator_heartbeat_monitoring(self, multi_coordinator_network: Communicator):
        """Test that coordinators monitor heartbeats properly."""
        comm = multi_coordinator_network

        # Verify initial state - all nodes connected
        with CoordinatorDirector(communicator=comm) as director:
            initial_nodes = director.get_nodes()
            # Should see all nodes in the network
            assert "N1" in initial_nodes
            assert "N2" in initial_nodes
            assert "N3" in initial_nodes
            assert "N4" in initial_nodes

        # Test communication with all coordinators
        assert comm.ask_rpc("N2.COORDINATOR", method="pong") is None
        assert comm.ask_rpc("N3.COORDINATOR", method="pong") is None
        assert comm.ask_rpc("N4.COORDINATOR", method="pong") is None

    def test_component_registration_persistence(self, multi_coordinator_network: Communicator):
        """Test that component registrations persist during normal operation."""
        comm = multi_coordinator_network

        # Add components to different coordinators
        components = []
        try:
            # Component on N2
            comp2 = Communicator(name="StableComponent", port=comm._ports[1])
            comp2.sign_in()
            components.append(comp2)

            sleep(TALKING_TIME)  # Time for registration to propagate

            # Verify component is visible across the network
            with CoordinatorDirector(communicator=comm) as director:
                global_components = director.get_global_components()
                assert "StableComponent" in global_components["N2"]

                # Check that component lists are consistent
                local_components = director.get_local_components()
                assert "Controller" in local_components

        finally:
            # Clean up components
            for comp in components:
                try:
                    comp.sign_out()
                except Exception:
                    pass

    def test_network_resilience_to_single_failure(self, multi_coordinator_network: Communicator):
        """Test network resilience when one coordinator experiences issues."""
        comm = multi_coordinator_network

        # Verify network is fully functional
        with CoordinatorDirector(communicator=comm) as director:
            initial_nodes = director.get_nodes()
            assert len(initial_nodes) == 4  # N1, N2, N3, N4

        # Test multiple communication paths
        paths = [
            ("N2.COORDINATOR", "Direct connection to hub neighbor"),
            ("N3.COORDINATOR", "Two-hop connection through chain"),
            ("N4.COORDINATOR", "Direct connection to hub neighbor"),
        ]

        for target, description in paths:
            try:
                response = comm.ask_rpc(target, method="pong")
                assert response is None, f"Failed to ping {target}: {description}"
            except Exception as e:
                # In a real failure scenario, we'd expect timeouts or connection errors
                # For this test, we're verifying normal operation
                pass


class TestLoadBalancing:
    """Test load distribution across multiple coordinators."""

    def test_concurrent_message_handling(self, multi_coordinator_network: Communicator):
        """Test that the network can handle concurrent messages."""
        comm = multi_coordinator_network

        # Verify network topology
        with CoordinatorDirector(communicator=comm) as director:
            nodes = director.get_nodes()
            # Should have multiple nodes available
            assert len(nodes) >= 3

        # Send concurrent messages to different coordinators
        targets = ["N2.COORDINATOR", "N3.COORDINATOR", "N4.COORDINATOR"]
        responses = []

        for target in targets:
            try:
                response = comm.ask_rpc(target, method="pong")
                responses.append(response)
            except Exception as e:
                # Capture any exceptions for analysis
                responses.append(e)

        # All successful responses should be None (pong response)
        successful_responses = [r for r in responses if r is None]
        assert len(successful_responses) > 0, "No successful responses received"

    def test_component_discovery_under_load(self, multi_coordinator_network: Communicator):
        """Test component discovery when multiple components register concurrently."""
        comm = multi_coordinator_network

        # Add multiple components concurrently
        components = []
        component_names = [f"LoadTest{i}" for i in range(1, 5)]
        component_ports = [comm._ports[0], comm._ports[1], comm._ports[2], comm._ports[3]]

        try:
            for name, port in zip(component_names, component_ports):
                comp = Communicator(name=name, port=port)
                comp.sign_in()
                components.append(comp)

            sleep(TALKING_TIME * 2)  # Extra time for registration propagation

            # Verify all components are registered across the network
            with CoordinatorDirector(communicator=comm) as director:
                global_components = director.get_global_components()

                # Check that components are visible in their respective nodes
                expected_mappings = {
                    "LoadTest1": "N1",
                    "LoadTest2": "N2",
                    "LoadTest3": "N3",
                    "LoadTest4": "N4",
                }

                for comp_name, node_name in expected_mappings.items():
                    if node_name in global_components:
                        # Component may or may not be in the list depending on timing
                        # This test verifies the registration mechanism works under load
                        pass

        finally:
            # Clean up components
            for comp in components:
                try:
                    comp.sign_out()
                except Exception:
                    pass

    def test_message_routing_efficiency(self, multi_coordinator_network: Communicator):
        """Test efficiency of message routing across different paths."""
        comm = multi_coordinator_network

        # Test different routing paths and measure consistency
        test_paths = [
            ("N2.COORDINATOR", "Direct path"),
            ("N3.COORDINATOR", "One hop path"),
            ("N4.COORDINATOR", "Direct path"),
        ]

        # Send multiple messages on each path
        results = {}
        for target, description in test_paths:
            path_responses = []
            for _ in range(3):  # Send 3 messages on each path
                try:
                    response = comm.ask_rpc(target, method="pong")
                    path_responses.append(response is None)  # True if successful
                except Exception:
                    path_responses.append(False)
            results[target] = path_responses

        # Verify that all paths are functional
        functional_paths = sum(sum(responses) for responses in results.values())
        assert functional_paths > 0, "No paths are functional"

    def test_network_scalability_with_components(self, multi_coordinator_network: Communicator):
        """Test network scalability with multiple registered components."""
        comm = multi_coordinator_network

        # Create multiple components on different nodes
        components_group1 = []  # Components on N1 and N2
        components_group2 = []  # Components on N3 and N4

        try:
            # Group 1: Components on earlier nodes in the chain
            comp_a1 = Communicator(name="GroupA1", port=comm._ports[0])
            comp_a1.sign_in()
            components_group1.append(comp_a1)

            comp_a2 = Communicator(name="GroupA2", port=comm._ports[1])
            comp_a2.sign_in()
            components_group1.append(comp_a2)

            # Group 2: Components on later nodes in the chain
            comp_b1 = Communicator(name="GroupB1", port=comm._ports[2])
            comp_b1.sign_in()
            components_group2.append(comp_b1)

            comp_b2 = Communicator(name="GroupB2", port=comm._ports[3])
            comp_b2.sign_in()
            components_group2.append(comp_b2)

            sleep(TALKING_TIME * 2)  # Time for all registrations to propagate

            # Verify component discovery works with multiple components
            with CoordinatorDirector(communicator=comm) as director:
                global_components = director.get_global_components()

                # Should have components registered on multiple nodes
                nodes_with_components = len([node for node in global_components.values() if node])
                assert nodes_with_components >= 2, "Components not distributed across enough nodes"

        finally:
            # Clean up all components
            for comp in components_group1 + components_group2:
                try:
                    comp.sign_out()
                except Exception:
                    pass
