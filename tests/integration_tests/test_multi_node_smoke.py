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
from time import sleep, time
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

# Port layout for N1 (base 62000) and N2 (base 62200)
N1_COORD_PORT = 62000
N1_DATA_XPUB = 62099
N1_DATA_XSUB = 62100
N1_DATA_GATHERER = 62101
N1_LOG_XPUB = 62097
N1_LOG_XSUB = 62098
N1_LOG_GATHERER = 62096

N2_COORD_PORT = 62200
N2_DATA_XPUB = 62299
N2_DATA_XSUB = 62300
N2_DATA_GATHERER = 62301
N2_LOG_XPUB = 62297
N2_LOG_XSUB = 62298
N2_LOG_GATHERER = 62296

SETUP_TIME = 1.0


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
        self.message_handler = CollectingPipeHandler(  # type: ignore
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
    actor.read_publish = readout  # type: ignore[method-assign]
    actor.connect()
    actor.listen(stop_event=stop_event)
    actor.disconnect()
    log_handler.close()
    root_logger.removeHandler(log_handler)


@pytest.fixture(scope="module")
def multi_node():
    ctx = zmq.Context()
    stop_events = [threading.Event() for _ in range(4)]

    threads: list[threading.Thread] = []

    # N1 Coordinator
    threads.append(
        threading.Thread(
            target=start_coordinator,
            kwargs=dict(namespace="N1", port=N1_COORD_PORT, stop_event=stop_events[0], context=ctx),
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
    sleep(SETUP_TIME)

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
    sleep(SETUP_TIME)

    # Connect N2 data distributor to N1 gatherer and vice versa
    dc_n2.connect_to_gatherer(f"localhost:{N1_DATA_GATHERER}")
    dc_n1.connect_to_gatherer(f"localhost:{N2_DATA_GATHERER}")
    # Connect N2 log distributor to N1 log gatherer and vice versa
    lc_n2.connect_to_gatherer(f"localhost:{N1_LOG_GATHERER}")
    lc_n1.connect_to_gatherer(f"localhost:{N2_LOG_GATHERER}")
    sleep(SETUP_TIME)

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
    sleep(SETUP_TIME * 2)

    # Data subscriber in N1
    sub_n1 = CollectingListener(name="monitor1", port=N1_COORD_PORT, data_port=N1_DATA_XPUB)
    sub_n1.start_listen()
    sub_n1.communicator.subscribe("")
    # Data subscriber in N2
    sub_n2 = CollectingListener(name="monitor2", port=N2_COORD_PORT, data_port=N2_DATA_XPUB)
    sub_n2.start_listen()
    sub_n2.communicator.subscribe("")
    # Log subscriber in N1
    log_sub_n1 = CollectingListener(name="logmon1", port=N1_COORD_PORT, data_port=N1_LOG_XPUB)
    log_sub_n1.start_listen()
    log_sub_n1.communicator.subscribe("")
    # Log subscriber in N2
    log_sub_n2 = CollectingListener(name="logmon2", port=N2_COORD_PORT, data_port=N2_LOG_XPUB)
    log_sub_n2.start_listen()
    log_sub_n2.communicator.subscribe("")
    sleep(SETUP_TIME)

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

    # Teardown
    for event in stop_events:
        event.set()
    for t in threads + [actor_thread]:
        t.join(timeout=1)
    for listener in (sub_n1, sub_n2, log_sub_n1, log_sub_n2):
        try:
            listener.close()
        except Exception:
            pass
    for dc in (dc_n1, dc_n2, lc_n1, lc_n2):
        try:
            dc.close()
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
        sleep(0.5)
        pub.send_data(data={"temperature": 42})
        assert wait_for_message(sub_n1.message_handler, lambda m: m.data == {"temperature": 42})
    finally:
        pub.close()


def test_data_cross_namespace(multi_node: dict):
    sub_n2 = multi_node["sub_n2"]
    sub_n2.message_handler._messages.clear()
    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        sleep(0.5)
        pub.send_data(data={"pressure": 1013.25})
        assert wait_for_message(sub_n2.message_handler, lambda m: m.data == {"pressure": 1013.25})
    finally:
        pub.close()


# ---------------------------------------------------------------------------
# Log protocol tests
# ---------------------------------------------------------------------------


def test_log_same_namespace(multi_node: dict):
    log_sub_n1 = multi_node["log_sub_n1"]
    log_sub_n1.message_handler._messages.clear()
    test_logger = logging.getLogger("test_log_same")
    test_logger.setLevel(logging.INFO)
    handler = ZmqLogHandler(
        context=multi_node["ctx"], host="localhost", port=N1_LOG_XSUB, full_name="N1.device"
    )
    test_logger.addHandler(handler)
    try:
        sleep(0.5)
        test_logger.info("smoke_test_log_same")
        assert wait_for_message(
            log_sub_n1.message_handler,
            lambda m: b"smoke_test_log_same" in (m.payload[0] if m.payload else b""),
        )
    finally:
        test_logger.removeHandler(handler)
        handler.close()


def test_log_cross_namespace(multi_node: dict):
    log_sub_n2 = multi_node["log_sub_n2"]
    log_sub_n2.message_handler._messages.clear()
    test_logger = logging.getLogger("test_log_cross")
    test_logger.setLevel(logging.INFO)
    handler = ZmqLogHandler(
        context=multi_node["ctx"], host="localhost", port=N1_LOG_XSUB, full_name="N1.device"
    )
    test_logger.addHandler(handler)
    try:
        sleep(0.5)
        test_logger.info("smoke_test_log_cross")
        assert wait_for_message(
            log_sub_n2.message_handler,
            lambda m: b"smoke_test_log_cross" in (m.payload[0] if m.payload else b""),
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
        d.disconnect_from_gatherer(f"localhost:{N1_DATA_GATHERER}")
    sleep(SETUP_TIME)

    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        sleep(0.5)
        pub.send_data(data={"test": "disconnect"})
        assert wait_for_message(
            sub_n1.message_handler, lambda m: m.data == {"test": "disconnect"}
        ), "N1 should still receive data"
        assert not wait_for_message(
            sub_n2.message_handler, lambda m: m.data == {"test": "disconnect"}, timeout=0.5
        ), "N2 should NOT receive data after disconnect"
    finally:
        pub.close()

    with DataCoordinatorDirector(actor="N2_DATA_COORDINATOR", port=N2_COORD_PORT, timeout=5) as d:
        d.connect_to_gatherer(f"localhost:{N1_DATA_GATHERER}")
    sleep(SETUP_TIME)


def test_reconnect_data_gatherer(multi_node: dict):
    sub_n2 = multi_node["sub_n2"]
    sub_n2.message_handler._messages.clear()

    pub = DataPublisher(
        full_name="N1.device", host="localhost", port=N1_DATA_XSUB, context=multi_node["ctx"]
    )
    try:
        sleep(0.5)
        pub.send_data(data={"test": "reconnect"})
        assert wait_for_message(
            sub_n2.message_handler, lambda m: m.data == {"test": "reconnect"}
        ), "N2 should receive data after reconnect"
    finally:
        pub.close()
