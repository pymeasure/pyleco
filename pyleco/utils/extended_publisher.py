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
from typing import Any

import numpy as np  # type: ignore[import-not-found]
import pint  # type: ignore[import-not-found]

from pyleco.utils.publisher import Publisher


class PowerEncoder(json.JSONEncoder):
    """Special json encoder for additional types like numpy, pint..."""

    def default(self, o: Any) -> Any:
        if isinstance(o, np.integer):
            return int(o)
        elif isinstance(o, np.floating):
            return float(o)
        elif isinstance(o, np.ndarray):
            return o.tolist()
        elif isinstance(o, pint.Quantity):
            return f"{o:~}"  # abbreviated units with '~'
        return super().default(o)


class ExtendedPublisher(Publisher):
    """
    Publishing key-value data via zmq.
    """

    def send(self, data: dict[str, Any]) -> None:
        """Send the dictionary `data`."""
        if self.full_name == "":
            raise ValueError("You have to specify the sender name, before sending!")
        else:
            self.socket.send_multipart((self.full_name.encode(),
                                        json.dumps(data, cls=PowerEncoder)))
