#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
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
from json import JSONDecodeError
from typing import Any, Callable, Generator, Union

from ..json_utils.errors import JSONRPCError, NODE_UNKNOWN, RECEIVER_UNKNOWN
from ..json_utils.json_objects import Notification
from ..core.message import Message, MessageTypes
from ..core.data_message import DataMessage
from ..json_utils.rpc_generator import RPCGenerator
from .data_publisher import DataPublisher

class ExtendedDataPublisher(DataPublisher):
    """A DataPublisher, which sends the data also via the control protocol."""

    def __init__(
        self, full_name: str, send_message_method: Callable[[Message], None], **kwargs
    ) -> None:
        super().__init__(full_name, **kwargs)
        self.send_control_message = send_message_method
        self.subscribers: set[bytes] = set()
        self.rpc_generator = RPCGenerator()

    def register_subscriber(self, subscriber: Union[bytes, str]) -> None:
        """Register a subscriber, that it may receive data messages via command protocol."""
        if isinstance(subscriber, str):
            subscriber = subscriber.encode()
        self.subscribers.add(subscriber)

    def unregister_subscriber(self, subscriber: Union[bytes, str]) -> None:
        """Unregister a subscriber, that it may not receive data messages via command protocol."""
        if isinstance(subscriber, str):
            subscriber = subscriber.encode()
        self.subscribers.discard(subscriber)

    def convert_data_message_to_messages(
        self, data_message: DataMessage, receivers: Union[set[Union[bytes, str]], set[bytes]],
    ) -> Generator[Message, Any, Any]:
        cid = data_message.conversation_id
        for receiver in receivers:
            yield Message(
                receiver=receiver,
                data=Notification("add_subscription_message"),
                conversation_id=cid,
                additional_payload=data_message.payload,
                message_type=MessageTypes.JSON,
            )

    def send_message(self, message: DataMessage) -> None:
        super().send_message(message)
        for msg in self.convert_data_message_to_messages(message, self.subscribers):
            # ideas: change to ask and check, whether it succeeded, otherwise remove subscriber
            self.send_control_message(msg)

    # TODO should unregister subscribers to which a message could not be forwarded
    def handle_json_error(self, message: Message) -> None:
        """Unregister unavailable subscribers.
        
        Call this method from the message handler, for example.
        """
        try:
            data: dict[str, Any] = message.data  # type: ignore
        except JSONDecodeError as exc:
            self.log.exception(f"Could not decode json message {message}", exc_info=exc)
            return
        try:
            self.rpc_generator.get_result_from_response(data)
        except JSONRPCError as exc:
            error_code = exc.rpc_error.code
            try:
                error_data = exc.rpc_error.data  # type: ignore
            except AttributeError:
                return
            if error_code == RECEIVER_UNKNOWN:
                self.unregister_subscriber(error_data)
            if error_code == NODE_UNKNOWN:
                if isinstance(error_data, str):
                    error_data = error_data.encode()
                for subscriber in self.subscribers:
                    if subscriber.startswith(error_data):
                        self.unregister_subscriber(subscriber)

