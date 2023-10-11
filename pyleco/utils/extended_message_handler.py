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

import json
import pickle
from typing import Union

import zmq

from .message_handler import MessageHandler
from ..core import PROXY_SENDING_PORT


class ExtendedMessageHandler(MessageHandler):
    """Message handler, which handles also data protocol messages."""

    def __init__(self, name: str, context: None | zmq.Context = None, **kwargs) -> None:
        super().__init__(name=name, context=context, **kwargs)
        self.context = context or zmq.Context.instance()
        self._subscriptions: list[bytes] = []  # List of all subscriptions

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method()(self.subscribe)
        self.rpc.method()(self.unsubscribe)
        self.rpc.method()(self.unsubscribe_all)

    def _listen_setup(self, host: str = "localhost", dataPort: int = PROXY_SENDING_PORT,
                      **kwargs) -> zmq.Poller:
        poller = super()._listen_setup(**kwargs)
        subscriber: zmq.Socket = self.context.socket(zmq.SUB)
        subscriber.connect(f"tcp://{host}:{dataPort}")
        self.subscriber = subscriber
        poller.register(subscriber, zmq.POLLIN)
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: int | None
                             ) -> dict[zmq.Socket, int]:
        socks = super()._listen_loop_element(poller=poller, waiting_time=waiting_time)
        if self.subscriber in socks:
            self.handle_subscriber_message()
            del socks[self.subscriber]
        return socks

    def _listen_close(self) -> None:
        self.subscriber.close(1)
        super()._listen_close()

    def handle_subscriber_message(self) -> None:
        subscriber = self.subscriber
        try:
            topic, content = subscriber.recv_multipart()
        except Exception as exc:
            self.log.exception("Invalid data", exc)
        else:
            try:
                data = {topic.decode(): pickle.loads(content)}
            except pickle.UnpicklingError:
                try:
                    data = {topic.decode(): json.loads(content)}
                except json.JSONDecodeError:
                    pass  # No valid data
                else:
                    self.handle_subscription_data(data)
            else:
                self.handle_subscription_data(data)

    def handle_subscription_data(self, data: dict) -> None:
        raise NotImplementedError

    def subscribe(self, topics: Union[str, list[str], tuple[str, ...]]) -> None:
        """Subscribe to a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self.subscribe_single(topic)
        else:
            self.subscribe_single(topics)

    def subscribe_single(self, topic: bytes | str) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        if topic not in self._subscriptions:
            self.log.debug(f"Subscribing to {topic!r}.")
            self.subscriber.subscribe(topic)
            self._subscriptions.append(topic)
        else:
            self.log.info(f"Already subscribed to {topic!r}.")

    def unsubscribe(self, topics: Union[str, list[str], tuple[str, ...]]) -> None:
        """Unsubscribe from a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self.unsubscribe_single(topic)
        else:
            self.unsubscribe_single(topics)

    def unsubscribe_single(self, topic: bytes | str) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        self.log.debug(f"Unsubscribing from {topic!r}.")
        self.subscriber.unsubscribe(topic)
        if topic in self._subscriptions:
            del self._subscriptions[self._subscriptions.index(topic)]

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all subscriptions."""
        while self._subscriptions:
            self.unsubscribe_single(self._subscriptions.pop())
