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

import json
import logging
import pickle
from typing import Any, Optional
from warnings import warn

import zmq

from ..core import PROXY_RECEIVING_PORT


class Publisher:
    """
    Publishing key-value data via zmq.

    :param str address: Address of the server, default is localhost.
    :param int port: Port of the server, defaults to 11100, default proxy.
    :param log: Logger to log to.
    :param bool standalone: Use without a proxy server.

    Sending dictionaries of measurement data to Data Collector Programs.

    The key is the first frame (for topic filtering) and the second frame
    contains the pickled value. Each pair is sent as their own message.
    Quantities may be expressed as a (magnitude number, units str) tuple.
    """

    fullname: str

    def __init__(self, host: str = "localhost", port: int = PROXY_RECEIVING_PORT,
                 log: Optional[logging.Logger] = None,
                 standalone: bool = False,
                 context: Optional[zmq.Context] = None,
                 fullname: str = "",
                 **kwargs) -> None:
        if log is None:
            self.log = logging.getLogger(f"{__name__}.Publisher")
        else:
            self.log = log.getChild("Publisher")
        self.log.info(f"Publisher started at {host}:{port}.")
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.PUB)
        if standalone:
            self._connecting = self.socket.bind
            self._disconnecting = self.socket.unbind
            self.host = "*"
        else:
            self._connecting = self.socket.connect
            self._disconnecting = self.socket.disconnect
            self.host = host
        self._port = 0
        self.port = port
        self.fullname = fullname
        super().__init__(**kwargs)

    def __del__(self) -> None:
        self.socket.close(1)

    def __call__(self, data: dict[str, Any]) -> None:
        """Publish the dictionary `data`."""
        self.send(data=data)

    @property
    def port(self) -> int:
        """The TCP port to publish to."""
        return self._port

    @port.setter
    def port(self, port: int) -> None:
        self.log.debug(f"Port changed to {port}.")
        if self._port == port:
            return
        if self._port:
            self._disconnecting(f"tcp://{self.host}:{self._port}")
        self._connecting(f"tcp://{self.host}:{port}")
        self._port = port

    def send(self, data: dict[str, Any]) -> None:
        """Send the dictionay `data`."""
        # TODO change to send the whole dictionary at once, in the future.
        assert isinstance(data, dict), "Data has to be a dictionary."
        for key, value in data.items():
            if not isinstance(value, (str, float, int, complex)):
                warn(
                    f"Data of type {type(value).__name__} might not be serializable in the future.",
                    FutureWarning)
            self.socket.send_multipart((key.encode(), pickle.dumps(value)))
            # for json:
            # dumped = json.dumps(data)

    def send_json(self, data: dict[str, Any]) -> None:
        """Send the dictionay `data`."""
        # TODO change to send the whole dictionary at once, in the future.
        assert isinstance(data, dict), "Data has to be a dictionary."
        for key, value in data.items():
            if not isinstance(value, (str, float, int, complex)):
                warn(
                    f"Data of type {type(value).__name__} might not be serializable in the future.",
                    FutureWarning)
            self.socket.send_multipart((key.encode(), json.dumps(value).encode()))

    def send_quantities(self, data: dict[str, Any]) -> None:
        """Send the dictionay `data` containing Quantities."""
        assert isinstance(data, dict), "Data has to be a dictionary."
        for key, value in data.items():
            self.socket.send_multipart((
                key.encode(),
                pickle.dumps((value.magnitude, f"{value.units:~}"))))

    def send_total(self, data: dict[str, Any]) -> None:
        """Send the whole data dictionary in one message, using the fullname."""
        if self.fullname == "":
            raise ValueError("You have to specify the sender name, before sending!")
        else:
            self.socket.send_multipart((self.fullname.encode(), json.dumps(data)))
