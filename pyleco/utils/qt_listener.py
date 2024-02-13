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

from qtpy.QtCore import QObject, Signal  # type: ignore
from zmq import Context  # type: ignore

from ..core.message import Message, MessageTypes
from ..core.data_message import DataMessage
from .listener import Listener, PipeHandler


class ListenerSignals(QObject):
    """Signals for the Listener."""
    dataReady = Signal(dict)
    message = Signal(Message)
    data_message = Signal(DataMessage)
    name_changed = Signal(str)


class QtPipeHandler(PipeHandler):

    local_methods = ["pong", "set_log_level"]

    def __init__(self, name: str, signals: ListenerSignals, context: Context | None = None,
                 **kwargs) -> None:
        self.signals = signals
        super().__init__(name, context, **kwargs)

    def handle_message(self, message: Message) -> None:
        if self.buffer.add_response_message(message):
            return
        elif message.header_elements.message_type == MessageTypes.JSON:
            try:
                method = message.data.get("method")  # type: ignore
            except AttributeError:
                pass
            else:
                if method in self.local_methods:
                    response = self.process_json_message(message=message)
                    self.send_message(response)
                    return
        # in all other cases:
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
    """
    Listening on published data and opening a configuration port. PyQt version.

    Call `listener.start_listen()` to actually listen.

    You may send a dictionary to the configuration port, which will be handed
    to the parent program via the 'command' signal. The listener responds with
    an acknowledgement or error.
    Special dictionary keys:
        - 'query': The listener does not respond, but places the response address
        into the 'query' entry, that the parent program may respond.
        - 'save': The listener does not respond, but emits a 'save' signal
        with the response address.

    :param int port: Configure the port to be used for configuration.
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
