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
from typing import Any, Iterable, Optional, Sequence, Union

from .core.message import Message
from .core.internal_protocols import CommunicatorProtocol
from .json_utils.rpc_generator import RPCGenerator


class FakeContext:
    """A fake context instance, similar to the result of `zmq.Context.instance()."""

    def socket(self, socket_type):
        return FakeSocket(socket_type)

    def term(self):
        self.closed = True

    def destroy(self, linger=0):
        self.closed = True


class FakeSocket:
    """A fake socket mirroring zmq.socket API, useful for unit tests.

    :attr list _s: contains a list of messages sent via this socket.
    :attr list _r: List of messages which can be read.
    """

    def __init__(self, socket_type: int, *args) -> None:
        self.closed: bool = False

        # Added for testing purposes
        self.addr: Union[None, str] = None
        self.socket_type: int = socket_type
        # they contain a list of messages sent/received
        self._s: list[list[bytes]] = []
        self._r: list[list[bytes]] = []
        if socket_type == 2:  # zmq.SUB
            # empirical data shots, that you have to unsubscribe as many times as you have
            # subscribed, therefore a list is best
            self._subscriptions: list[bytes] = []

    def bind(self, addr: str) -> None:
        self.addr = addr

    def bind_to_random_port(self, addr: str, *args, **kwargs) -> int:
        self.addr = addr
        return 5

    def unbind(self, addr: Optional[str] = None) -> None:
        self.addr = None

    def connect(self, addr: str):
        self.addr = addr

    def disconnect(self, addr: Optional[str] = None) -> None:
        self.addr = None

    def poll(self, timeout: Optional[int] = None,
             flags: int = "PollEvent.POLLIN") -> int:  # type: ignore
        """Poll the socket for events.

        :returns: poll event mask (POLLIN, POLLOUT), 0 if the timeout was reached without an event.
        """
        return 1 if len(self._r) else 0

    def recv_multipart(self, flags: int = 0, *, copy: bool = True, track: bool = False
                       ) -> list[bytes]:
        return self._r.pop(0)

    def send_multipart(self, msg_parts: Sequence, flags: int = 0, copy: bool = True,
                       track: bool = False, **kwargs) -> None:
        for i, part in enumerate(msg_parts):
            if not isinstance(part, bytes):
                # Similar to real error message.
                raise TypeError(f"Frame {i} ({part}) does not support the buffer interface.")
        self._s.append(list(msg_parts))

    def subscribe(self, topic: Union[str, bytes]) -> None:
        if self.socket_type != 2:
            raise ValueError("Invalid argument")  # type is a ZMQError
        else:
            if isinstance(topic, str):
                topic = topic.encode()
            self._subscriptions.append(topic)

    def unsubscribe(self, topic: Union[str, bytes]) -> None:
        if self.socket_type != 2:
            raise ValueError("Invalid argument")  # type is a ZMQError
        else:
            if isinstance(topic, str):
                topic = topic.encode()
            try:
                self._subscriptions.remove(topic)
            except ValueError:
                pass  # not present

    def close(self, linger: Optional[int] = None) -> None:
        self.addr = None
        self.closed = True


class FakePoller:
    """A fake zmq poller."""
    def __init__(self) -> None:
        self._sockets: list[FakeSocket] = []

    def poll(self, timeout: Optional[int] = None) -> list[tuple[FakeSocket, Any]]:
        """Returns a list of events (socket, event_mask)"""
        events = []
        for sock in self._sockets:
            if sock.poll(timeout=timeout):
                events.append((sock, 1))
        return events

    def register(self, socket,
                 flags: int = "PollEvent.POLLIN",  # type: ignore
                 ) -> None:
        self._sockets.append(socket)

    def unregister(self, socket: FakeSocket) -> None:
        try:
            self._sockets.remove(socket)
        except ValueError:
            pass  # already removed


class FakeCommunicator(CommunicatorProtocol):
    """Contains lists with received (`_r`) and sent (`_s`) messages."""

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.rpc_generator = RPCGenerator()
        self._r: list[Message] = []
        self._s: list[Message] = []

    def sign_in(self) -> None:
        self._signed_in = True

    def sign_out(self) -> None:
        self._signed_in = False

    def close(self) -> None:
        self._closed = True

    def send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.name.encode()
        self._s.append(message)

    def read_message(self, conversation_id: Optional[bytes] = None, timeout=None):
        return self._r.pop(0)

    def ask_message(self, message: Message, timeout=None) -> Message:
        self.send_message(message)
        return self.read_message(timeout=timeout)


class FakeDirector:
    """Supplements a regular director to create a fake one for testing.

    If you want to test the `SomeDirector` class, which directs `SomeActor`, you can create a
    subclass of the `FakeDirector` and `SomeDirector`.
    The newly created director will verify that methods are present in the `SomeActor` class,
    defined in the `remote_class` parameter.
    That way you can test, that `SomeDirector` calls an existing remote method.

    ..code::

        class FakeSomeDirector(FakeDirector, SomeDirector):
            pass

        @pytest.fixture
        def some_director():
            return FakeSomeDirector(remote_class=SomeActor)

        def test_some_method(some_director):
            # arrange
            some_director.return_value = 7  # define return value
            # act
            some_director.ask_rpc(method="method_name", arg1=5)  # returns 7
            # assert that the correct method name and kwargs are called
            assert some_director.method == "method_name"
            assert some_director.kwargs == {"arg1": 5}

    """

    return_value: Any  # value which the remote method should return
    method: str  # called method
    kwargs: dict[str, Any]  # kwargs sent to the method

    def __init__(self, remote_class, **kwargs):
        kwargs.setdefault("communicator", FakeCommunicator("communicator"))
        super().__init__(**kwargs)
        self.remote_class = remote_class

    def ask_rpc(
        self,
        method: str,
        actor: Optional[Union[bytes, str]] = None,
        additional_payload: Optional[Iterable[bytes]] = None,
        extract_additional_payload: bool = False,
        **kwargs,
    ) -> Any:
        assert hasattr(self.remote_class, method), f"Remote class does not have method '{method}'."
        self.method = method
        self.kwargs = kwargs
        return self.return_value

    def ask_rpc_async(
        self,
        method: str,
        actor: Optional[Union[bytes, str]] = None,
        additional_payload: Optional[Iterable[bytes]] = None,
        **kwargs,
    ) -> bytes:
        assert hasattr(self.remote_class, method), f"Remote class does not have method '{method}'."
        self.method = method
        self.kwargs = kwargs
        return b"conversation_id;"
