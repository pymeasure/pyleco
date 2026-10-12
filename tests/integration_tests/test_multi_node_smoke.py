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
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Multi-node smoke test: two namespaces with full LECO stack (control + data + log)."""

from __future__ import annotations

import logging
import threading
from time import time
from typing import Any, Callable

import pytest
import zmq

from pyleco.actors.actor import Actor
from pyleco.coordinators.coordinator import Coordinator
from pyleco.coordinators.data_coordinator import DataCoordinator
from pyleco.core.data_message import DataMessage
from pyleco.directors.coordinator_director import CoordinatorDirector
from pyleco.directors.data_coordinator_director import DataCoordinatorDirector
from pyleco.directors.director import Director
from pyleco.utils.data_publisher import DataPublisher
from pyleco.utils.listener import Listener
from pyleco.utils.pipe_handler import PipeHandler
from pyleco.utils.zmq_log_handler import ZmqLogHandler

from helpers import (
    component_ready,
    coordinator_ready,
    reserve_free_ports,
    send_until_visible,
)
from helpers import wait_for

pytestmark = pytest.mark.timeout(300)  # heavy module fixture: 2 coordinators + 4 data servers

# Port layout for N1 (base 62000) and N2 (base 62200): if any member of a layout
# (coordinator port plus the derived log/data ports below) is blocked by
# lingering sockets of a previous run, the whole layout is shifted upwards.
N1_OFFSETS = (0, 96, 97, 98, 99, 100, 101)
N1_COORD_PORT = reserve_free_ports(62000, N1_OFFSETS)
N1_LOG_GATHERER = N1_COORD_PORT + 96
N1_LOG_XPUB = N1_COORD_PORT + 97
N1_LOG_XSUB = N1_COORD_PORT + 98
N1_DATA_XPUB = N1_COORD_PORT + 99
N1_DATA_XSUB = N1_COORD_PORT + 100
N1_DATA_GATHERER = N1_COORD_PORT + 101

N2_COORD_PORT = reserve_free_ports(max(62200, N1_COORD_PORT + 102), N1_OFFSETS)
N2_LOG_GATHERER = N2_COORD_PORT + 96
N2_LOG_XPUB = N2_COORD_PORT + 97
N2_LOG_XSUB = N2_COORD_PORT + 98
N2_DATA_XPUB = N2_COORD_PORT + 99
N2_DATA_XSUB = N2_COORD_PORT + 100
N2_DATA_GATHERER = N2_COORD_PORT + 101

N1_DATA_GATHERER_ADDRESS = f"localhost:{N1_DATA_GATHERER}"


def wait_for_message(
    handler: CollectingPipeHandler,
    predicate: Callable[[DataMessage], bool],
    timeout: float = 2.0,
) -> bool:
    with handler._condition:
        if any(predicate(m) for m in handler._messages):
            return True
        deadline = time() + timeout
        remaining = timeout
        while remaining > 0:
            handler._condition.wait(timeout=remaining)
            if any(predicate(m) for m in handler._messages):
                return True
            remaining = deadline - time()
    return False


class CollectingPipeHandler(PipeHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._messages: list[DataMessage] = []
        self._condition = threading.Condition()

    def handle_subscription_message(self, message: DataMessage) -> None:
        self._messages.append(message)
        with self._condition:
            self._condition.notify_all()

    def handle_subscription_data(self, data: dict) -> None:
        pass


class CollectingListener(Listener):
    message_handler: CollectingPipeHandler

    def _listen(
        self,
        name: str,
        stop_event: threading.Event,
        coordinator_host: str,
        coordinator_port: int,
        data_host: str,
        data_port: int,
    ) -> None:
        self.message_handler = CollectingPipeHandler(  # type: ignore[reportIncompatibleVariableOverride]
            name,
            host=coordinator_host,
            port=coordinator_port,
            data_host=data_host,
            data_port=data_port,
        )
        self.message_handler.listen(stop_event=stop_event)


class FakeInstrument:
    _prop1 = 5

    def __init__(self) -> None:
        pass

    def connect(self) -> None:
        pass

    @property
    def constant(self) -> int:
        return 7

    @property
    def prop1(self) -> int:
        return self._prop1

    @prop1.setter
    def prop1(self, value: int) -> None:
        self._prop1 = value

    def triple(self, factor: float = 1, factor2: float = 1) -> float:
        return factor * factor2 * 3


def readout(device: FakeInstrument, publisher: DataPublisher) -> None:
    publisher.send_data(data={"temperature": 42})


def start_coordinator(
    namespace: str,
    port: int,
    stop_event: threading.Event,
    context: zmq.Context,
    coordinators: list[str] | None = None,
) -> None:
    with Coordinator(namespace=namespace, port=port, context=context) as coordinator:
        coordinator.routing(coordinators=coordinators, stop_event=stop_event)


def start_actor(
    stop_event: threading.Event, coord_port: int, data_xsub_port: int, ctx: zmq.Context
) -> None:
    root_logger = logging.getLogger(f"actor_{coord_port}")
    root_logger.setLevel(logging.DEBUG)
    log_handler = ZmqLogHandler(
        context=ctx, host="localhost", port=N1_LOG_XSUB, full_name="N1.device"
    )
    root_logger.addHandler(log_handler)

    actor = Actor("device", FakeInstrument, port=coord_port, context=ctx)
    actor.publisher = DataPublisher(
        full_name=actor.full_name, host="localhost", port=data_xsub_port, context=ctx
    )
    actor.read_publish = readout
    actor.connect()
    actor.listen(stop_event=stop_event)
    actor.disconnect()
    log_handler.close()
    root_logger.removeHandler(log_handler)


def send_and_confirm(
    pub: DataPublisher,
    handler: CollectingPipeHandler,
    data: dict,
    timeout: float = 5.0,
) -> bool:
    """Send `data` via `pub` until a message with it arrived at the `handler`.

    The first message(s) from a freshly connected PUB socket may be dropped by
    the zmq slow joiner problem, therefore sending is retried until the message
    is seen or `timeout` elapses (a dropped message cannot be waited for).
    """
    return send_until_visible(
        lambda: pub.send_data(data=data),
        lambda: wait_for_message(handler, lambda m: m.data == data, timeout=0.0),
        timeout=timeout,
    )


def payload_marker_check(handler: CollectingPipeHandler, marker: bytes) -> Callable[[], bool]:
    """Whether a `marker` is contained in the first payload frame of any message."""

    def check() -> bool:
        return any(marker in (m.payload[0] if m.payload else b"") for m in handler._messages)

    return check


def log_message_probe(logger: logging.Logger, message: str, handler: CollectingPipeHandler) -> bool:
    """Log `message` via the `logger` until the marker reached the `handler`."""
    return send_until_visible(
        lambda: logger.info(message),
        payload_marker_check(handler, message.encode()),
    )


@pytest.fixture(scope="module")
def multi_node():
    ctx = zmq.Context()
    stop_events = [threading.Event() for _ in range(4)]

    threads: list[threading.Thread] = []
    coordinators: list[DataCoordinator] = []
    listeners: list[CollectingListener] = []
    actor_thread: threading.Thread | None = None
    try:
        # N1 Coordinator
        threads.append(
            threading.Thread(
                target=start_coordinator,
                kwargs=dict(
                    namespace="N1", port=N1_COORD_PORT, stop_event=stop_events[0], context=ctx
                ),
                daemon=True,
            )
        )
        # N2 Coordinator
        threads.append(
            threading.Thread(
                target=start_coordinator,
                kwargs=dict(
                    namespace="N2",
                    port=N2_COORD_PORT,
                    stop_event=stop_events[1],
                    context=ctx,
                    coordinators=[f"localhost:{N1_COORD_PORT}"],
                ),
                daemon=True,
            )
        )

        for t in threads:
            t.start()
        assert wait_for(lambda: coordinator_ready(N1_COORD_PORT), timeout=10), (
            "Coordinator N1 did not come up."
        )
        assert wait_for(lambda: coordinator_ready(N2_COORD_PORT), timeout=10), (
            "Coordinator N2 did not come up."
        )

        # N1 DataCoordinator
        dc_n1 = DataCoordinator(
            name="N1_DATA_COORDINATOR",
            host="localhost",
            coordinator_port=N1_COORD_PORT,
            xsub_port=N1_DATA_XSUB,
            gatherer_xpub_port=N1_DATA_GATHERER,
            xpub_port=N1_DATA_XPUB,
            context=ctx,
        )
        coordinators.append(dc_n1)
        # N2 DataCoordinator
        dc_n2 = DataCoordinator(
            name="N2_DATA_COORDINATOR",
            host="localhost",
            coordinator_port=N2_COORD_PORT,
            xsub_port=N2_DATA_XSUB,
            gatherer_xpub_port=N2_DATA_GATHERER,
            xpub_port=N2_DATA_XPUB,
            context=ctx,
        )
        coordinators.append(dc_n2)
        # N1 LogCoordinator
        lc_n1 = DataCoordinator(
            name="N1_LOG_COORDINATOR",
            host="localhost",
            coordinator_port=N1_COORD_PORT,
            xsub_port=N1_LOG_XSUB,
            gatherer_xpub_port=N1_LOG_GATHERER,
            xpub_port=N1_LOG_XPUB,
            context=ctx,
        )
        coordinators.append(lc_n1)
        # N2 LogCoordinator
        lc_n2 = DataCoordinator(
            name="N2_LOG_COORDINATOR",
            host="localhost",
            coordinator_port=N2_COORD_PORT,
            xsub_port=N2_LOG_XSUB,
            gatherer_xpub_port=N2_LOG_GATHERER,
            xpub_port=N2_LOG_XPUB,
            context=ctx,
        )
        coordinators.append(lc_n2)

        # Connect N2 data distributor to N1 gatherer and vice versa
        dc_n2.connect_to_gatherer(N1_DATA_GATHERER_ADDRESS)
        dc_n1.connect_to_gatherer(f"localhost:{N2_DATA_GATHERER}")
        # Connect N2 log distributor to N1 log gatherer and vice versa
        lc_n2.connect_to_gatherer(f"localhost:{N1_LOG_GATHERER}")
        lc_n1.connect_to_gatherer(f"localhost:{N2_LOG_GATHERER}")

        # Actor in N1
        actor_thread = threading.Thread(
            target=start_actor,
            kwargs=dict(
                stop_event=stop_events[2],
                coord_port=N1_COORD_PORT,
                data_xsub_port=N1_DATA_XSUB,
                ctx=ctx,
            ),
            daemon=True,
        )
        actor_thread.start()
        assert wait_for(lambda: component_ready(N1_COORD_PORT, "device"), timeout=10), (
            "Actor 'device' did not register."
        )

        # Data subscriber in N1
        sub_n1 = CollectingListener(name="monitor1", port=N1_COORD_PORT, data_port=N1_DATA_XPUB)
        sub_n1.start_listen()
        sub_n1.communicator.subscribe("")
        listeners.append(sub_n1)
        # Data subscriber in N2
        sub_n2 = CollectingListener(name="monitor2", port=N2_COORD_PORT, data_port=N2_DATA_XPUB)
        sub_n2.start_listen()
        sub_n2.communicator.subscribe("")
        listeners.append(sub_n2)
        # Log subscriber in N1
        log_sub_n1 = CollectingListener(name="logmon1", port=N1_COORD_PORT, data_port=N1_LOG_XPUB)
        log_sub_n1.start_listen()
        log_sub_n1.communicator.subscribe("")
        listeners.append(log_sub_n1)
        # Log subscriber in N2
        log_sub_n2 = CollectingListener(name="logmon2", port=N2_COORD_PORT, data_port=N2_LOG_XPUB)
        log_sub_n2.start_listen()
        log_sub_n2.communicator.subscribe("")
        listeners.append(log_sub_n2)
        for coordinator_port, name in (
            (N1_COORD_PORT, "monitor1"),
            (N2_COORD_PORT, "monitor2"),
            (N1_COORD_PORT, "logmon1"),
            (N2_COORD_PORT, "logmon2"),
        ):
            assert wait_for(lambda p=coordinator_port, n=name: component_ready(p, n), timeout=10), (
                f"Listener '{name}' did not register."
            )

        # Positive readiness proof of the data paths (incl. subscriptions on the
        # distributors and the cross-node gatherer links, slow joiner included).
        with DataPublisher(
            full_name="N1.readiness", host="localhost", port=N1_DATA_XSUB, context=ctx
        ) as pub:
            assert send_and_confirm(pub, sub_n1.message_handler, {"readiness": "N1"}), (
                "Data pipeline towards N1 not ready."
            )
            assert send_and_confirm(pub, sub_n2.message_handler, {"readiness": "N2"}), (
                "Cross-node data pipeline towards N2 not ready."
            )
        # Positive readiness proof of the log paths.
        log_handler = ZmqLogHandler(
            context=ctx, host="localhost", port=N1_LOG_XSUB, full_name="N1.readiness"
        )
        probe_logger = logging.getLogger("log_readiness_probe")
        probe_logger.setLevel(logging.INFO)
        probe_logger.addHandler(log_handler)
        try:
            assert log_message_probe(probe_logger, "readiness_check", log_sub_n1.message_handler), (
                "Log pipeline towards N1 not ready."
            )
            assert log_message_probe(probe_logger, "readiness_check", log_sub_n2.message_handler), (
                "Cross-node log pipeline towards N2 not ready."
            )
        finally:
            probe_logger.removeHandler(log_handler)
            log_handler.close()

        yield {
            "ctx": ctx,
            "stop_events": stop_events,
            "threads": threads + [actor_thread],
            "dc_n1": dc_n1,
            "dc_n2": dc_n2,
            "lc_n1": lc_n1,
            "lc_n2": lc_n2,
            "sub_n1": sub_n1,
            "sub_n2": sub_n2,
            "log_sub_n1": log_sub_n1,
            "log_sub_n2": log_sub_n2,
        }

    finally:
        # Teardown: stop everything created so far, also when a setup assert
        # above failed, so leftovers never leak into the next module.
        for event in stop_events:
            event.set()
        all_threads = threads + ([actor_thread] if actor_thread is not None else [])
        for t in all_threads:
            t.join(timeout=5)
        for listener in listeners:
            try:
                listener.close()
            except Exception:
                pass
        for coordinator in coordinators:
            try:
                coordinator.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Control protocol tests
# ---------------------------------------------------------------------------


def test_control_local_rpc(multi_node: dict):
    with Director(actor="device", port=N1_COORD_PORT, timeout=5) as director:
        result = director.get_parameters("constant")
    assert result == {"constant": 7}


def test_control_cross_namespace_rpc(multi_node: dict):
    with Director(actor="N1.device", port=N2_COORD_PORT, timeout=5) as director:
        result = director.call_action("triple", factor=3)
    assert result == 9


# ---------------------------------------------------------------------------
# Data protocol tests
# ---------------------------------------------------------------------------


def test_data_same_namespace(multi_node: dict):
    sub_n1 = multi_node["sub_n1"]
    sub_n1.message_handler._messages.clear()
    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        assert send_and_confirm(pub, sub_n1.message_handler, {"temperature": 42}), (
            "N1 should receive data."
        )
    finally:
        pub.close()


def test_data_cross_namespace(multi_node: dict):
    sub_n2 = multi_node["sub_n2"]
    sub_n2.message_handler._messages.clear()
    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        assert send_and_confirm(pub, sub_n2.message_handler, {"pressure": 1013.25}), (
            "N2 should receive cross-namespace data."
        )
    finally:
        pub.close()


# ---------------------------------------------------------------------------
# Log protocol tests
# ---------------------------------------------------------------------------


def test_log_same_namespace(multi_node: dict):
    log_sub_n1 = multi_node["log_sub_n1"]
    message = "smoke_test_log_same"
    log_sub_n1.message_handler._messages.clear()
    test_logger = logging.getLogger(f"test_{message}")
    test_logger.setLevel(logging.INFO)
    handler = ZmqLogHandler(
        context=multi_node["ctx"], host="localhost", port=N1_LOG_XSUB, full_name="N1.device"
    )
    test_logger.addHandler(handler)
    try:
        assert log_message_probe(test_logger, message, log_sub_n1.message_handler), (
            "N1 should receive the log message."
        )
    finally:
        test_logger.removeHandler(handler)
        handler.close()


def test_log_cross_namespace(multi_node: dict):
    log_sub_n2 = multi_node["log_sub_n2"]
    message = "smoke_test_log_cross"
    log_sub_n2.message_handler._messages.clear()
    test_logger = logging.getLogger(f"test_{message}")
    test_logger.setLevel(logging.INFO)
    handler = ZmqLogHandler(
        context=multi_node["ctx"], host="localhost", port=N1_LOG_XSUB, full_name="N1.device"
    )
    test_logger.addHandler(handler)
    try:
        assert log_message_probe(test_logger, message, log_sub_n2.message_handler), (
            "N2 should receive the cross-namespace log message."
        )
    finally:
        test_logger.removeHandler(handler)
        handler.close()


# ---------------------------------------------------------------------------
# Directory propagation test
# ---------------------------------------------------------------------------


def test_global_components_visible(multi_node: dict):
    with CoordinatorDirector(port=N1_COORD_PORT, timeout=5) as d:
        components = d.get_global_components()
    assert "N1" in components
    assert "N2" in components
    n1_comps = components.get("N1", [])
    n2_comps = components.get("N2", [])
    assert "device" in n1_comps
    assert "monitor2" in n2_comps


# ---------------------------------------------------------------------------
# Dynamic gatherer connect/disconnect tests
# ---------------------------------------------------------------------------


def test_disconnect_data_gatherer(multi_node: dict):
    sub_n1 = multi_node["sub_n1"]
    sub_n2 = multi_node["sub_n2"]
    sub_n1.message_handler._messages.clear()
    sub_n2.message_handler._messages.clear()

    with DataCoordinatorDirector(actor="N2_DATA_COORDINATOR", port=N2_COORD_PORT, timeout=5) as d:
        d.disconnect_from_gatherer(N1_DATA_GATHERER_ADDRESS)
        # Verify the disconnect took effect (connection table of N2's coordinator).
        assert not wait_for(lambda: N1_DATA_GATHERER_ADDRESS in d.list_gatherers(), timeout=5), (
            "Disconnect did not take effect."
        )

    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        assert send_and_confirm(pub, sub_n1.message_handler, {"test": "disconnect"}), (
            "N1 should still receive data."
        )
        # Generous absence window so that no in-flight message can contradict.
        assert not wait_for_message(
            sub_n2.message_handler, lambda m: m.data == {"test": "disconnect"}, timeout=2.0
        ), "N2 should NOT receive data after disconnect."
    finally:
        pub.close()

    with DataCoordinatorDirector(actor="N2_DATA_COORDINATOR", port=N2_COORD_PORT, timeout=5) as d:
        d.connect_to_gatherer(N1_DATA_GATHERER_ADDRESS)
        assert wait_for(lambda: N1_DATA_GATHERER_ADDRESS in d.list_gatherers(), timeout=5), (
            "Reconnect did not take effect."
        )


def test_reconnect_data_gatherer(multi_node: dict):
    sub_n2 = multi_node["sub_n2"]
    sub_n2.message_handler._messages.clear()

    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        assert send_and_confirm(pub, sub_n2.message_handler, {"test": "reconnect"}), (
            "N2 should receive data after reconnect."
        )
    finally:
        pub.close()
