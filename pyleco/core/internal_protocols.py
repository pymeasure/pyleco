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

"""
These classes show pyleco's internal API of tools that talk with the LECO protocol.

They are not defined by LECO itself as it does not touch the message transfer.

Any Component could use these tools in order to send and read messsages.
For example a Director might use these tools to direct an Actor.
"""

from typing import Any, Optional, Protocol

from .leco_protocols import ComponentProtocol
from .message import Message
from .rpc_generator import RPCGenerator


class CommunicatorProtocol(ComponentProtocol, Protocol):
    """A helper class for a Component, to communicate via the LECO protocol.

    For example a Director might use such a class to send/read messages to/from an Actor.
    """

    name: str
    namespace: Optional[str] = None
    rpc_generator: RPCGenerator

    def sign_in(self) -> None: ...  # pragma: no cover

    def sign_out(self) -> None: ...  # pragma: no cover

    def send(self,
             receiver: bytes | str,
             conversation_id: Optional[bytes] = None,
             data: Optional[Any] = None,
             **kwargs) -> None:
        """Send a message based on kwargs."""
        self.send_message(message=Message(
            receiver=receiver, conversation_id=conversation_id, data=data, **kwargs
        ))

    def send_message(self, message: Message) -> None: ...  # pragma: no cover

    def ask(self, receiver: bytes | str, conversation_id: Optional[bytes] = None,
            data: Optional[Any] = None,
            **kwargs) -> Message:
        """Send a message based on kwargs and retrieve the response."""
        return self.ask_message(message=Message(
            receiver=receiver, conversation_id=conversation_id, data=data, **kwargs))

    def ask_message(self, message: Message) -> Message: ...  # pragma: no cover

    def close(self) -> None: ...  # pragma: no cover
