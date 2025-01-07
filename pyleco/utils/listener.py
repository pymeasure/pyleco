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
import logging
from threading import Thread, Event
from time import sleep
from typing import Any, Callable, Optional, Union

from ..core import PROXY_SENDING_PORT, COORDINATOR_PORT
from .pipe_handler import PipeHandler, CommunicatorPipe

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Listener:
    """Listening on incoming messages in a separate thread.

    On one side it handles incoming messages (data and control protocol) in another thread.
    On the other side, it offers the :meth:`get_communicator` method, which returns a
    :class:`Communicator`, offering communication to the network.

    Call :meth:`.start_listen()` to actually listen.

    ..code::

        listener = Listener()
        listener.start_listen()  # starts a message handler in another thread
        communicator = listener.get_communicator()  # get a Communicator endpoint for this thread
        response = communicator.ask_message(some_message_object)

    :param name: Name to listen under for control commands.
    :param int data_port: Port number for the data protocol.
    :param logger: Logger instance whose logs should be published. Defaults to "__main__".
    """

    communicator: CommunicatorPipe
    message_handler: PipeHandler

    def __init__(self,
                 name: str,
                 host: str = "localhost",
                 port: int = COORDINATOR_PORT,
                 data_host: Optional[str] = None,
                 data_port: int = PROXY_SENDING_PORT,
                 logger: Optional[logging.Logger] = None,
                 timeout: float = 1,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        log.info(f"Start Listener for '{name}'.")

        self.name = name
        self.logger = logger
        self.timeout = timeout

        self.coordinator_address = host, port
        self.data_address = data_host or host, data_port

    def close(self) -> None:
        """Close everything."""
        self.stop_listen()

    @property
    def name(self) -> str:
        try:
            return self.communicator.name
        except AttributeError:
            return self._name

    @name.setter
    def name(self, value: str) -> None:
        self._name = value
        try:
            self.communicator.name = value
        except AttributeError:
            pass

    # Methods to control the Listener
    def start_listen(self) -> None:
        """Start to listen in a thread."""
        self.stop_listen()
        self.stop_event = Event()
        self.thread = Thread(
            target=self._listen,
            args=(
                self.name,
                self.stop_event,
                self.coordinator_address[0],
                self.coordinator_address[1],
                self.data_address[0],
                self.data_address[1],
            ))
        self.thread.daemon = True
        self.thread.start()
        for _ in range(10):
            sleep(0.05)
            try:
                self.communicator: CommunicatorPipe = self.message_handler.get_communicator(
                    timeout=self.timeout)
            except AttributeError:
                pass
            else:
                log.addHandler(self.message_handler.log_handler)
                if self.logger is not None:
                    self.logger.addHandler(self.message_handler.log_handler)
                return
        raise TimeoutError("PipeHandler has not started after 0.5 s.")

    def get_communicator(self, **kwargs) -> CommunicatorPipe:
        """Get the communicator for the calling thread, creating one if necessary."""
        kwargs.setdefault("timeout", self.timeout)
        return self.message_handler.get_communicator(**kwargs)

    def register_rpc_method(self, method: Callable[..., Any], **kwargs) -> None:
        """Register a method for calling with the current message handler.

        If you restart the listening, you have to register the method anew.
        """
        self.message_handler.register_rpc_method(method=method, **kwargs)

    def register_binary_rpc_method(
        self,
        method: Callable[..., Union[Any, tuple[Any, list[bytes]]]],
        accept_binary_input: bool = False,
        return_binary_output: bool = False,
        **kwargs,
    ) -> None:
        """Register a binary method for calling with the current message handler.

        If you restart the listening, you have to register the method anew.
        """
        self.message_handler.register_binary_rpc_method(
            method=method,
            accept_binary_input=accept_binary_input,
            return_binary_output=return_binary_output,
            **kwargs,
        )

    def stop_listen(self) -> None:
        """Stop the listener Thread."""
        try:
            if self.thread.is_alive():
                log.debug("Stopping listener thread.")
                self.stop_event.set()
                self.thread.join()
                self.message_handler.close()
                log.removeHandler(self.message_handler.log_handler)
                if self.logger is not None:
                    self.logger.removeHandler(self.message_handler.log_handler)
        except AttributeError:
            pass

    """
    Methods below are executed in the thread, DO NOT CALL DIRECTLY!
    """

    def _listen(self, name: str, stop_event: Event, coordinator_host: str, coordinator_port: int,
                data_host: str, data_port: int) -> None:
        """Start a PipeHandler, which has to be executed in a separate thread."""
        self.message_handler = PipeHandler(name, host=coordinator_host, port=coordinator_port,
                                           data_host=data_host, data_port=data_port)
        self.message_handler.listen(stop_event=stop_event)
