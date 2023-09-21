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

from typing import Optional, Sequence

from .core.message import Message
from .core.internal_protocols import CommunicatorProtocol
from .core.rpc_generator import RPCGenerator


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
        self.addr: None | str = None
        self.socket_type: int = socket_type
        # they contain a list of messages sent/received
        self._s: list[list[bytes]] = []
        self._r: list[list[bytes]] = []

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
        # print(parts)
        for i, part in enumerate(msg_parts):
            if not isinstance(part, bytes):
                # Similar to real error message.
                raise TypeError(f"Frame {i} ({part}) does not support the buffer interface.")
        self._s.append(list(msg_parts))

    def close(self, linger: Optional[int] = None) -> None:
        self.addr = None
        self.closed = True


class FakeCommunicator(CommunicatorProtocol):
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

    def ask_message(self, message: Message) -> Message:
        self.send_message(message)
        return self._r.pop(0)
