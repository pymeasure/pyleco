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
import pytest
from time import sleep
from typing import Any

import zmq

from pyleco.core.data_message import DataMessage
from pyleco.utils.data_publisher import DataPublisher
from pyleco.utils.listener import Listener
from pyleco.utils.pipe_handler import PipeHandler

from pyleco.coordinators.proxy_server import start_proxy, port


pytestmark = pytest.mark.filterwarnings("ignore::FutureWarning")


offset = 100


class CollectingPipeHandler(PipeHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._messages: list[DataMessage] = []

    def handle_subscription_message(self, message: DataMessage) -> None:
        self._messages.append(message)


class ModListener(Listener):
    message_handler: CollectingPipeHandler

    def _listen(
        self,
        name: str,
        stop_event,
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


@pytest.fixture(scope="module")
def proxy_handle():
    ctx = zmq.Context()
    handle = start_proxy(context=ctx, offset=offset)
    yield handle
    handle.close()


@pytest.fixture(scope="module")
def publisher(proxy_handle) -> DataPublisher:
    return DataPublisher(full_name="abc", port=port - 2 * offset, context=proxy_handle.context)


@pytest.fixture(scope="module")
def listener(publisher: DataPublisher, proxy_handle):
    listener = ModListener(name="listener", data_port=port - 1 - 2 * offset)
    listener.start_listen()
    listener.communicator.subscribe("")
    sleep(2)
    yield listener
    listener.close()


def test_publishing(publisher: DataPublisher, listener: ModListener):
    listener.message_handler._messages.clear()
    publisher.send_data(topic="topic", data={"key": "value"})
    sleep(0.1)
    msgs = listener.message_handler._messages
    assert len(msgs) >= 1
    found = any(m.topic == b"topic" and m.data == {"key": "value"} for m in msgs)
    assert found
