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

from PyQt6 import QtCore  # type: ignore

from ..core.message import Message
from .listener import Listener


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

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name=name, **kwargs)
        self.signals = self.ListenerSignals()

    local_methods = ["pong", "set_log_level"]

    class ListenerSignals(QtCore.QObject):
        """Signals for the Listener."""
        dataReady = QtCore.pyqtSignal(dict)
        message = QtCore.pyqtSignal(Message)

    def handle_subscription_data(self, data: dict) -> None:
        """Handle incoming subscription data."""
        self.signals.dataReady.emit(data)

    def start_listen(self, host: str | None = None, dataPort: int | None = None) -> None:
        super().start_listen(host, dataPort)
        self.message_handler.handle_subscription_data = self.handle_subscription_data
        self.message_handler.finish_handle_commands = self.finish_handle_commands

    def finish_handle_commands(self, message: Message) -> None:
        """Handle the list of commands: Redirect them to the application."""
        try:
            method = message.data.get("method")  # type: ignore
        except AttributeError:
            method = None
        if method in self.local_methods:
            self.message_handler.finish_handle_commands(message)
        else:
            self.signals.message.emit(message)
