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

import logging
from typing import Any, Optional

import zmq

from ..core import PROXY_RECEIVING_PORT
from ..core.data_message import DataMessage


class DataPublisher:
    """
    Publishing data via the LECO data protocol.

    :param str name: Name of the publishing Component
    :param str address: Address of the server, default is localhost.
    :param int port: Port of the server, defaults to 11100, default proxy.
    :param log: Logger to log to.

    Sending :class:`DataMessage` via the data protocol.

    Quantities may be expressed as a (magnitude number, units str) tuple.
    """

    fullname: str

    def __init__(self,
                 fullname: str,
                 host: str = "localhost", port: int = PROXY_RECEIVING_PORT,
                 log: Optional[logging.Logger] = None,
                 context: Optional[zmq.Context] = None,
                 **kwargs) -> None:
        if log is None:
            self.log = logging.getLogger(f"{__name__}.Publisher")
        else:
            self.log = log.getChild("Publisher")
        self.log.info(f"Publisher started at {host}:{port}.")
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.PUB)
        self.socket.connect(f"tcp://{host}:{port}")
        self.fullname = fullname
        super().__init__(**kwargs)

    def __del__(self) -> None:
        self.socket.close(1)

    def __call__(self, data: Any) -> None:
        """Publish `data`."""
        self.send_data(data=data)

    def send_message(self, message: DataMessage) -> None:
        """Send a data protocol message."""
        self.socket.send_multipart(message.to_frames())

    def send_data(self, data: Any) -> None:
        """Send the `data` via the data protocol."""
        message = DataMessage(self.fullname, data=data)
        self.send_message(message)