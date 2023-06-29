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

from typing import List

from .core.message import Message
from .core.protocols import Communicator
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

    def __init__(self, socket_type, *args):
        self.socket_type = socket_type
        self.addr = None
        self._s = []
        self._r = []
        self.closed = False

    def bind(self, addr):
        self.addr = addr

    def bind_to_random_port(self, addr, *args, **kwargs):
        self.addr = addr
        return 5

    def unbind(self, addr=None):
        self.addr = None

    def connect(self, addr):
        self.addr = addr

    def disconnect(self, addr=None):
        self.addr = None

    def poll(self, timeout=0, flags="PollEvent.POLLIN"):
        return 1 if len(self._r) else 0

    def recv_multipart(self):
        return self._r.pop(0)

    def send_multipart(self, parts):
        print(parts)
        for i, part in enumerate(parts):
            if not isinstance(part, bytes):
                # Similar to real error message.
                raise TypeError(f"Frame {i} ({part}) does not support the buffer interface.")
        self._s.append(list(parts))

    def close(self, linger=None):
        self.addr = None
        self.closed = True


class FakeCommunicator(Communicator):
    def __init__(self, name: str):
        super().__init__()
        self.name = name
        self.rpc_generator = RPCGenerator()
        self._r: List[Message] = []
        self._s: List[Message] = []

    def sign_in(self) -> None:
        return super().sign_in()

    def sign_out(self) -> None:
        return super().sign_out()

    def close(self) -> None:
        return super().close()

    def send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.name.encode()
        self._s.append(message)

    def ask_message(self, message: Message) -> Message:
        self.send_message(message)
        return self._r.pop(0)
