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
import pickle

import zmq


# Classes of the data protocol
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

    def __init__(self, host="localhost", port=11100, log=None,
                 standalone=False,
                 **kwargs):
        if log is None:
            self.log = logging.getLogger(f"{__name__}.Publisher")
        else:
            self.log = log.getChild("Publisher")
        self.log.info(f"Publisher started at {host}:{port}.")
        self.socket = zmq.Context.instance().socket(zmq.PUB)
        if standalone:
            self._connecting = self.socket.bind
            self._disconnecting = self.socket.unbind
            self.host = "*"
        else:
            self._connecting = self.socket.connect
            self._disconnecting = self.socket.disconnect
            self.host = host
        self._port = False
        self.port = port
        super().__init__(**kwargs)

    def __del__(self):
        self.socket.close(1)

    def __call__(self, data):
        """Publish the dictionary `data`."""
        self.send(data)

    @property
    def port(self):
        """The TCP port to publish to."""
        return self._port

    @port.setter
    def port(self, port):
        self.log.debug(f"Port changed to {port}.")
        if self._port == port:
            return
        if self._port:
            self._disconnecting(f"tcp://{self.host}:{self._port}")
        self._connecting(f"tcp://{self.host}:{port}")
        self._port = port

    def send(self, data):
        """Send the dictionay `data`."""
        assert isinstance(data, dict), "Data has to be a dictionary."
        for key, value in data.items():
            self.socket.send_multipart((key.encode(), pickle.dumps(value)))

    def send_quantities(self, data):
        """Send the dictionay `data` containing Quantities."""
        assert isinstance(data, dict), "Data has to be a dictionary."
        for key, value in data.items():
            self.socket.send_multipart((
                key.encode(),
                pickle.dumps((value.magnitude, f"{value.units:~}"))))
