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
from typing import Any, Optional
from warnings import warn

import zmq

from ..core import PROXY_RECEIVING_PORT
from .data_publisher import DataPublisher


try:
    import numpy as np  # type: ignore[import-not-found]
    import pint  # type: ignore[import-not-found]
except ModuleNotFoundError:
    pint = False  # type: ignore[assignment]

if pint:
    class PowerEncoder(json.JSONEncoder):
        """Special json encoder for additional types like numpy, pint..."""

        def default(self, o: Any) -> Any:
            if isinstance(o, np.integer):
                return int(o)
            elif isinstance(o, np.floating):
                return float(o)
            elif isinstance(o, np.ndarray):
                return o.tolist()
            elif isinstance(o, pint.Quantity):  # type: ignore
                return f"{o:~}"  # abbreviated units with '~'
            return super().default(o)
else:
    PowerEncoder = json.JSONEncoder  # type: ignore


class Publisher(DataPublisher):
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

    def __init__(self, host: str = "localhost", port: int = PROXY_RECEIVING_PORT,
                 log: Optional[logging.Logger] = None,
                 standalone: bool | None = None,
                 context: Optional[zmq.Context] = None,
                 fullname: str = "",
                 **kwargs) -> None:
        super().__init__(host=host,
                         port=port,
                         log=log,
                         context=context,
                         full_name=fullname,
                         **kwargs)
        if standalone is not None:
            warn("Standalone does not work anymore", FutureWarning)

    def __call__(self, data: dict[str, Any]) -> None:
        """Publish the dictionary `data`."""
        warn("Publisher is deprecated, use DataPublisher instead.", FutureWarning)
        self.send_legacy(data=data)

    def send_legacy_json(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            # 235 is message type for legacy json: publish variable name as topic and json
            self.send_data(topic=key, data=json.dumps(value, cls=PowerEncoder), message_type=235)

    def send(self, data: dict[str, Any]) -> None:
        """Send the dictionay `data`."""
        self.send_legacy(data=data)
