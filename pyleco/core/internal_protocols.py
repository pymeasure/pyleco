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

"""
These classes show pyleco's internal API of tools that talk with the LECO protocol.

They are not defined by LECO itself as it does not touch the message transfer.

Any Component could use these tools in order to send and read messages.
For example a Director might use these tools to direct an Actor.
"""

from __future__ import annotations
from typing import Any, Optional, Protocol, Iterable, Union

from .message import Message, MessageTypes
from ..json_utils.rpc_generator import RPCGenerator


class CommunicatorProtocol(Protocol):
    """A helper class for a Component, to communicate via the LECO protocol.

    For example a Director might use such a class to send/read messages to/from an Actor.
    """

    name: str
    namespace: Optional[str] = None
    rpc_generator: RPCGenerator
    timeout: float = 1  # default reading timeout in seconds

    @property
    def full_name(self) -> str:
        return self.name if self.namespace is None else ".".join((self.namespace, self.name))

    def sign_in(self) -> None: ...  # pragma: no cover

    def sign_out(self) -> None: ...  # pragma: no cover

    def send_message(self, message: Message) -> None: ...  # pragma: no cover

    def read_message(
        self, conversation_id: Optional[bytes], timeout: Optional[float] = None
    ) -> Message: ...  # pragma: no cover

    def ask_message(
        self, message: Message, timeout: Optional[float] = None
    ) -> Message: ...  # pragma: no cover

    def close(self) -> None: ...  # pragma: no cover

    # Utilities
    def send(
        self,
        receiver: Union[bytes, str],
        conversation_id: Optional[bytes] = None,
        data: Optional[Any] = None,
        **kwargs,
    ) -> None:
        """Send a message based on kwargs."""
        self.send_message(
            message=Message(receiver=receiver, conversation_id=conversation_id, data=data, **kwargs)
        )

    def ask(
        self,
        receiver: Union[bytes, str],
        conversation_id: Optional[bytes] = None,
        data: Optional[Any] = None,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> Message:
        """Send a message based on kwargs and retrieve the response."""
        return self.ask_message(
            message=Message(
                receiver=receiver, conversation_id=conversation_id, data=data, **kwargs
            ),
            timeout=timeout,
        )

    def interpret_rpc_response(
        self, response_message: Message, extract_additional_payload: bool = False
    ) -> Union[Any, tuple[Any, list[bytes]]]:
        """Retrieve the return value of a RPC response and optionally the additional payload."""
        result = self.rpc_generator.get_result_from_response(response_message.payload[0])
        if extract_additional_payload:
            return result, response_message.payload[1:]
        else:
            return result

    def ask_rpc(
        self,
        receiver: Union[bytes, str],
        method: str,
        timeout: Optional[float] = None,
        additional_payload: Optional[Iterable[bytes]] = None,
        extract_additional_payload: bool = False,
        **kwargs,
    ) -> Any:
        """Send a JSON-RPC request (with method \\**kwargs) and return the response value."""
        string = self.rpc_generator.build_request_str(method=method, **kwargs)
        response = self.ask(
            receiver=receiver,
            data=string,
            message_type=MessageTypes.JSON,
            additional_payload=additional_payload,
            timeout=timeout,
        )
        return self.interpret_rpc_response(
            response, extract_additional_payload=extract_additional_payload
        )


class SubscriberProtocol(Protocol):
    """A helper class to subscribe to data protocol topics."""

    def subscribe_single(self, topic: bytes) -> None: ...  # pragma: no cover

    def unsubscribe_single(self, topic: bytes) -> None: ...  # pragma: no cover

    def unsubscribe_all(self) -> None: ...  # pragma: no cover

    def subscribe(self, topics: Union[str, Iterable[str]]) -> None:
        """Subscribe to a topic or list of topics."""
        if isinstance(topics, str):
            self.subscribe_single(topics.encode())
        else:
            for topic in topics:
                self.subscribe_single(topic.encode())

    def unsubscribe(self, topics: Union[str, Iterable[str]]) -> None:
        """Unsubscribe to a topic or list of topics."""
        if isinstance(topics, str):
            self.unsubscribe_single(topics.encode())
        else:
            for topic in topics:
                self.unsubscribe_single(topic.encode())
