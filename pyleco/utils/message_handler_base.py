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
from time import perf_counter
from typing import Optional
import zmq

from ..core.message import Message
from ..utils.base_communicator import BaseCommunicator
from ..utils.events import Event, SimpleEvent


# Parameters
heartbeat_interval = 10  # s


class MessageHandlerBase(BaseCommunicator):
    """Base class for message handlers with core listening functionality.

    Handles:
    - Message listening loop
    - Heartbeat management
    - Sign-in/sign-out sequence
    - Basic message receiving

    Subclasses should implement protocol-specific message handling.
    """

    next_beat: float  #: Time of next heartbeat
    stop_event: Event  #: Event to stop the listening loop

    def listen(self, stop_event: Event = SimpleEvent(), waiting_time: int = 100, **kwargs) -> None:
        """Listen for zmq communication until `stop_event` is set or until KeyboardInterrupt.

        :param stop_event: Event to stop the listening loop.
        :param waiting_time: Time to wait for a readout signal in ms.
        """
        self.stop_event = stop_event
        poller = self._listen_setup(**kwargs)
        try:
            while not stop_event.is_set():
                self._listen_loop_element(poller=poller, waiting_time=waiting_time)
        except KeyboardInterrupt:
            pass  # User stops the loop
        finally:
            self._listen_close(waiting_time=waiting_time)

    def _listen_setup(self) -> zmq.Poller:
        """Setup for listening.

        If you add your own sockets, remember to poll only for incoming messages.
        """
        self.log.info(f"Starting to listen as '{self.name}'.")
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)
        self.sign_in()
        self.next_beat = perf_counter() + heartbeat_interval
        return poller

    def _listen_loop_element(
        self, poller: zmq.Poller, waiting_time: Optional[int]
    ) -> dict[zmq.Socket, int]:
        """Check sockets for incoming messages and handle them.

        :param waiting_time: Timeout of the poller in ms.
        """
        socks = dict(poller.poll(waiting_time))
        if self.socket in socks:
            self.read_and_handle_message()
            del socks[self.socket]
        elif (now := perf_counter()) > self.next_beat:
            self.heartbeat()
            self.next_beat = now + heartbeat_interval
        return socks

    def _listen_close(self, waiting_time: Optional[int] = None) -> None:
        """Close the listening loop."""
        self.log.info(f"Stopping to listen as '{self.name}'.")
        self.sign_out()

    def read_and_handle_message(self) -> None:
        """Read and process an incoming message, which has not been requested."""
        try:
            message = self.read_message(timeout=0)
        except TimeoutError:
            return
        self.log.debug(f"Handling message {message}")
        if not message.payload:
            return  # no payload, that means just a heartbeat
        self.handle_message(message=message)

    def handle_message(self, message: Message) -> None:
        """Handle an incoming message (to be implemented by subclasses)."""
        raise NotImplementedError("Subclasses must implement message handling logic.")
