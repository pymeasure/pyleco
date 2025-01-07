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
import pytest
from time import sleep

from pyleco.utils.data_publisher import DataPublisher
from pyleco.utils.listener import Listener
from pyleco.core import PROXY_SENDING_PORT

from pyleco.coordinators.proxy_server import start_proxy, port


pytestmark = pytest.mark.skip("Hangs on teardown in CI")


# Parameters
offset = 100


class ModListener(Listener):
    def __init__(self, name: str, host: str = "localhost", data_port: int = PROXY_SENDING_PORT,
                 **kwargs) -> None:
        super().__init__(name=name, host=host, data_port=data_port, **kwargs)
        self._data: list[dict] = []

    def handle_subscription_data(self, data: dict) -> None:
        self._data.append(data)


@pytest.fixture(scope="module")
def publisher() -> DataPublisher:
    return DataPublisher(full_name="abc", port=port - 2 * offset)


@pytest.fixture(scope="module")
def listener(publisher):
    context = start_proxy(offset=offset)
    listener = ModListener(name="listener", data_port=port - 1 - 2 * offset)
    listener.start_listen()
    listener.communicator.subscribe("")
    sleep(.5)  # due to slow joiner: Allow time for connections.
    yield listener  # type: ignore
    listener.close()
    context.destroy()  # in order to stop the proxy


def test_publishing(publisher: DataPublisher, listener: ModListener):
    publisher.send_data(topic="topic", data="value")
    sleep(.1)
    assert listener._data == [{"topic": "value"}]
