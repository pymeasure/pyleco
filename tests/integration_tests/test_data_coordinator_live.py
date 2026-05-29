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

import threading
from time import sleep
from typing import Any

import pytest
import zmq

from pyleco.coordinators.coordinator import Coordinator
from pyleco.coordinators.data_coordinator import DataCoordinator
from pyleco.core.data_message import DataMessage
from pyleco.directors.director import Director
from pyleco.utils.data_publisher import DataPublisher
from pyleco.utils.listener import Listener
from pyleco.utils.pipe_handler import PipeHandler

COORDINATOR_PORT = 61200
XSUB_PORT = 61300
GATHERER_XPUB_PORT = 61301
XPUB_PORT = 61299
SETUP_TIME = 0.5


class CollectingPipeHandler(PipeHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._messages: list[DataMessage] = []

    def handle_subscription_message(self, message: DataMessage) -> None:
        self._messages.append(message)

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
        self.message_handler = CollectingPipeHandler(
            name,
            host=coordinator_host,
            port=coordinator_port,
            data_host=data_host,
            data_port=data_port,
        )
        self.message_handler.listen(stop_event=stop_event)


def start_coordinator(
    namespace: str, port: int, stop_event: threading.Event, context: zmq.Context, **kwargs: Any
):
    with Coordinator(namespace=namespace, port=port, context=context, **kwargs) as coordinator:
        coordinator.routing(stop_event=stop_event)


@pytest.fixture(scope="module")
def data_coordinator_setup():
    ctx = zmq.Context()
    stop_event = threading.Event()
    coord_thread = threading.Thread(
        target=start_coordinator,
        kwargs=dict(namespace="N1", port=COORDINATOR_PORT, stop_event=stop_event, context=ctx),
        daemon=True,
    )
    coord_thread.start()
    sleep(SETUP_TIME)

    dc = DataCoordinator(
        name="DATA_COORDINATOR",
        host="localhost",
        coordinator_port=COORDINATOR_PORT,
        xsub_port=XSUB_PORT,
        gatherer_xpub_port=GATHERER_XPUB_PORT,
        xpub_port=XPUB_PORT,
        context=ctx,
    )
    pub = DataPublisher(full_name="publisher", port=XSUB_PORT, context=ctx)
    sub = CollectingListener(name="subscriber", port=COORDINATOR_PORT, data_port=XPUB_PORT)
    sub.start_listen()
    sub.communicator.subscribe("")
    sleep(SETUP_TIME)

    yield dc, pub, sub

    sub.close()
    pub.close()
    dc.close()
    stop_event.set()
    coord_thread.join(timeout=2)
    ctx.destroy(linger=0)


def test_publish_subscribe(data_coordinator_setup):
    dc, pub, sub = data_coordinator_setup
    sub.message_handler._messages.clear()
    pub.send_data(topic="topic", data={"key": "value"})
    sleep(0.3)
    msgs = sub.message_handler._messages
    assert len(msgs) >= 1
    found = any(m.topic == b"topic" and m.data == {"key": "value"} for m in msgs)
    assert found


def test_multiple_messages(data_coordinator_setup):
    dc, pub, sub = data_coordinator_setup
    sub.message_handler._messages.clear()
    pub.send_data(topic="temp", data=42)
    sleep(0.1)
    pub.send_data(topic="pressure", data=1013.25)
    sleep(0.1)
    msgs = sub.message_handler._messages
    assert len(msgs) >= 2
    topics_data = {m.topic.decode(): m.data for m in msgs}
    assert "temp" in topics_data
    assert topics_data["temp"] == 42
    assert "pressure" in topics_data
    assert topics_data["pressure"] == 1013.25


def test_rpc_send_data_addresses(data_coordinator_setup):
    dc, pub, sub = data_coordinator_setup
    with Director(actor="DATA_COORDINATOR", port=COORDINATOR_PORT) as director:
        result = director.ask_rpc(method="send_data_addresses")
    assert result is not None
    assert "gatherer_xsub" in result
    assert "gatherer_xpub" in result
    assert "distributor_xpub" in result


def test_raw_zmq_pub_sub():
    ctx = zmq.Context()
    with DataCoordinator(
        name="DC_RAW",
        host="localhost",
        xsub_port=XSUB_PORT + 100,
        gatherer_xpub_port=GATHERER_XPUB_PORT + 100,
        xpub_port=XPUB_PORT + 100,
        start_listener=False,
        context=ctx,
    ):
        pub = ctx.socket(zmq.PUB)
        pub.connect(f"tcp://localhost:{XSUB_PORT + 100}")
        sub = ctx.socket(zmq.SUB)
        sub.connect(f"tcp://localhost:{XPUB_PORT + 100}")
        sub.subscribe(b"")
        sleep(SETUP_TIME)

        frames = [b"topic", b"header", b"payload"]
        pub.send_multipart(frames)
        sleep(0.1)

        assert sub.poll(timeout=1000)
        received = sub.recv_multipart()
        assert received == frames

        sub.close()
        pub.close()
    ctx.destroy(linger=0)


def test_data_coordinator_close():
    ctx = zmq.Context()
    dc = DataCoordinator(
        name="DC_CLOSE",
        host="localhost",
        xsub_port=XSUB_PORT + 200,
        gatherer_xpub_port=GATHERER_XPUB_PORT + 200,
        xpub_port=XPUB_PORT + 200,
        start_listener=False,
        context=ctx,
    )
    assert not dc.closed
    dc.close()
    assert dc.closed
    ctx.destroy(linger=0)
