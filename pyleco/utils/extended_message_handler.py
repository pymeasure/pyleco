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
import json
import pickle
from typing import Optional

import zmq

from .message_handler import MessageHandler
from ..core import PROXY_SENDING_PORT
from ..core.data_message import DataMessage
from ..core.internal_protocols import SubscriberProtocol


class ExtendedMessageHandler(MessageHandler, SubscriberProtocol):
    """Message handler, which handles also data protocol messages."""

    def __init__(self,
                 name: str,
                 context: Optional[zmq.Context] = None,
                 host: str = "localhost",
                 data_host: Optional[str] = None,
                 data_port: int = PROXY_SENDING_PORT,
                 **kwargs) -> None:
        if context is None:
            context = zmq.Context.instance()
        super().__init__(name=name, context=context, host=host, **kwargs)
        self._subscriptions: list[bytes] = []  # List of all subscriptions
        self.subscriber: zmq.Socket = context.socket(zmq.SUB)
        if data_host is None:
            data_host = host
        self.subscriber.connect(f"tcp://{data_host}:{data_port}")

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.subscribe)
        self.register_rpc_method(self.unsubscribe)
        self.register_rpc_method(self.unsubscribe_all)

    def close(self) -> None:
        self.subscriber.close(1)
        return super().close()

    def _listen_setup(self, **kwargs) -> zmq.Poller:
        poller = super()._listen_setup(**kwargs)
        poller.register(self.subscriber, zmq.POLLIN)
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: Optional[int]
                             ) -> dict[zmq.Socket, int]:
        socks = super()._listen_loop_element(poller=poller, waiting_time=waiting_time)
        if self.subscriber in socks:
            self.read_subscription_message()
            del socks[self.subscriber]
        return socks

    def read_subscription_message(self) -> None:
        """Read a message from the data protocol."""
        try:
            message = DataMessage.from_frames(*self.subscriber.recv_multipart())
        except Exception as exc:
            self.log.exception("Invalid data", exc)
            return
        if message.message_type > 200:
            # legacy style: topic is a variable name!
            self.handle_full_legacy_subscription_message(message)
        else:
            self.handle_subscription_message(message)

    def handle_subscription_message(self, message: DataMessage) -> None:
        """Handle a message read from the data protocol and handle it."""
        raise NotImplementedError

    def handle_full_legacy_subscription_message(self, message: DataMessage) -> None:
        """Handle an illegal subscription message (topic is variable name)."""
        if message.message_type == 234:
            value = pickle.loads(message.payload[0])
        elif message.message_type == 235:
            value = json.loads(message.payload[0])
        else:
            raise ValueError("Legacy long message cannot be handled")
        self.handle_subscription_data({message.topic.decode(): value})

    def handle_subscription_data(self, data: dict) -> None:
        # TODO deprecated
        raise NotImplementedError

    def subscribe_single(self, topic: bytes) -> None:
        if topic not in self._subscriptions:
            self.log.debug(f"Subscribing to {topic!r}.")
            self._subscriptions.append(topic)
            self.subscriber.subscribe(topic)
        else:
            self.log.info(f"Already subscribed to {topic!r}.")

    def unsubscribe_single(self, topic: bytes) -> None:
        self.log.debug(f"Unsubscribing from {topic!r}.")
        self.subscriber.unsubscribe(topic)
        if topic in self._subscriptions:
            self._subscriptions.remove(topic)

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all subscriptions."""
        while self._subscriptions:
            self.unsubscribe_single(self._subscriptions.pop())
