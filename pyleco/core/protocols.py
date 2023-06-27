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

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Tuple

from .message import Message
from ..core.rpc_generator import RPCGenerator


"""
These classes show the remotely available methods via rpc.
"""


class Component(Protocol):
    """Any Component of the pyleco protocol."""

    def pong(self) -> None:
        """Respond to any request."""
        return  # always succeeds.


class ExtendedComponent(Component, Protocol):
    """A Component which supports more features."""

    def set_log_level(self, level: int) -> None: ...

    def shutdown(self) -> None: ...


class Coordinator(Component, Protocol):
    """A command protocol Coordinator"""

    def sign_in(self) -> None: ...

    def sign_out(self) -> None: ...

    def coordinator_sign_in(self) -> None: ...

    def coordinator_sign_out(self) -> None: ...

    def set_nodes(self) -> None: ...

    def sign_in2(self) -> None: ...

    def sign_in3(self) -> None: ...


class Actor(Component, Protocol):
    """An Actor Component."""

    def get_properties(self, properties: List[str] | Tuple[str, ...]) -> Dict[str, Any]: ...

    def set_properties(self, properties: Dict[str, Any]) -> None: ...

    def call_method(self, method: str, _args: Optional[list | tuple] = None, **kwargs) -> Any: ...

class PollingActor(Actor, Protocol):
    """An Actor which allows regular polling."""

    polling_interval: float

    def start_polling(self, polling_interval: Optional[float]) -> None: ...

    def set_polling_interval(self, polling_interval: float) -> None: ...

    def get_polling_interval(self) -> float: ...

    def stop_polling(self) -> None: ...


class LockingActor(Actor, Protocol):
    """An Actor which allows to lock the device or channels of the device."""

    def lock(self, resource: Optional[str] = None) -> bool: ...

    def unlock(self, resource: Optional[str] = None) -> None: ...

    def force_unlock(self, resource: Optional[str] = None) -> None: ...


"""
These classes show the API of tools, which talk with the LECO protocol.

Any Component could use these tools in order to send and read messsages.
For example a Director might use these tools to direct an Actor.
"""


class Communicator(Component, Protocol):
    """A helper class for a Component, to communicate via the LECO protocol."""

    name: str
    node: str | None = None
    rpc_generator: RPCGenerator

    # TODO include?
    # def __init__(
    #         self,
    #         name: str,
    #         host: str = "localhost",
    #         port: int = 12300,
    #         protocol: str = "tcp",
    #         **kwargs
    # ) -> None:
    #     self.name = name

    def sign_in(self) -> None: ...

    def sign_out(self) -> None: ...

    def send(self,
             receiver: str | bytes,
             conversation_id: bytes = b"",
             data: Optional[Any] = None,
             **kwargs) -> None:
        """Send a message based on kwargs."""
        self.send_message(message=Message(
            receiver=receiver, conversation_id=conversation_id, data=data, **kwargs
        ))

    def send_message(self, message: Message) -> None: ...

    # TODO implement?
    # def poll(self, timeout: float | None = 0) -> bool: ...

    # def read(self) -> Message: ...

    def ask(self, receiver: bytes | str, conversation_id: bytes = b"",
            data: Optional[Any] = None,
            **kwargs) -> Message:
        """Send a message based on kwargs and retrieve the response."""
        return self.ask_message(message=Message(
            receiver=receiver, conversation_id=conversation_id, data=data, **kwargs))

    def ask_message(self, message: Message) -> Message: ...

    def close(self) -> None: ...
