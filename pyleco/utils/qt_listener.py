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

from typing import Optional

from qtpy.QtCore import QObject, Signal  # type: ignore
from zmq import Context  # type: ignore

from ..core.message import Message
from ..core.data_message import DataMessage
from .listener import Listener, PipeHandler


class ListenerSignals(QObject):
    """Signals for the Listener."""
    # General
    name_changed = Signal(str)
    # Control protocol
    json_request_message = Signal(Message)
    json_error_message = Signal(Message)
    json_result_message = Signal(Message)
    message = Signal(Message)  # emitted in the same cases as above messages.
    # Data Protocol
    dataReady = Signal(dict)
    data_message = Signal(DataMessage)


class QtPipeHandler(PipeHandler):

    local_methods = ["pong", "set_log_level"]

    def __init__(self, name: str, signals: ListenerSignals, context: Optional[Context] = None,
                 **kwargs) -> None:
        self.signals = signals
        super().__init__(name, context, **kwargs)

    def handle_json_request(self, message: Message) -> None:
        try:
            method = message.data.get("method")  # type: ignore
        except AttributeError:
            pass
        else:
            if method in self.local_methods:
                super().handle_json_request(message=message)
                return
        # in all other cases:
        self.signals.message.emit(message)
        self.signals.json_request_message.emit(message)

    def handle_json_error(self, message: Message) -> None:
        self.signals.message.emit(message)
        self.signals.json_error_message.emit(message)

    def handle_json_result(self, message: Message) -> None:
        self.signals.message.emit(message)
        self.signals.json_result_message.emit(message)

    def handle_unknown_message_type(self, message: Message) -> None:
        self.signals.message.emit(message)

    def handle_subscription_data(self, data: dict) -> None:
        """Handle incoming subscription data."""
        # old style
        self.signals.dataReady.emit(data)

    def handle_subscription_message(self, message: DataMessage) -> None:
        """Handle an incoming subscription message."""
        # new style
        self.signals.data_message.emit(message)


class QtListener(Listener):
    """Listening on incoming messages in a separate thread - PyQt version.

    On one side it handles incoming messages (data and control protocol) in another thread.
    On the other side, it offers the :meth:`get_communicator` method, which returns a
    :class:`Communicator`, offering communication to the network.

    Call :meth:`.start_listen()` to actually listen.

    It emits signals from :attr:`signals` if a control or data message arrives.
    It also emits the `signals.name_changed` signal, whenever the Communicator changes its name.

    :param int data_port: Configure the port to be used for configuration.
    :param logger: Logger instance whose logs should be published. Defaults to "__main__".
    """

    def __init__(self, name: str, host: str = "localhost", **kwargs) -> None:
        super().__init__(name=name, host=host, **kwargs)
        self.signals = ListenerSignals()

    def _listen(self, name: str, stop_event, coordinator_host: str, coordinator_port: int,
                data_host: str, data_port: int) -> None:
        self.message_handler = QtPipeHandler(name, signals=self.signals,
                                             host=coordinator_host, port=coordinator_port,
                                             data_host=data_host, data_port=data_port,)
        self.message_handler.register_on_name_change_method(self.signals.name_changed.emit)
        self.message_handler.listen(stop_event=stop_event)
