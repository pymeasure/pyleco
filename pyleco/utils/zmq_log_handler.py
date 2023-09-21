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
from logging.handlers import QueueHandler
import time
from typing import Any, Optional

import zmq

from ..core import LOG_RECEIVING_PORT


class ZmqLogHandler(QueueHandler):
    """Handle log entries publishing them.

    You have to set the :attr:`fullname` in order to publish logs.

    :attr fullname: Full name of the Component.
    """

    fullname: str

    def __init__(self, context: Optional[zmq.Context] = None, host: str = "localhost",
                 port: int = LOG_RECEIVING_PORT, fullname: str = "") -> None:
        context = context or zmq.Context.instance()
        socket: zmq.Socket = context.socket(zmq.PUB)
        socket.connect(f"tcp://{host}:{port}")
        super().__init__(socket)  # type: ignore
        self.fullname = fullname

    def prepare(self, record: logging.LogRecord) -> list[str]:
        """Prepare a json serializable message from the record in order to send it."""
        record.message = record.getMessage()
        record.asctime = time.strftime('%Y-%m-%d %H:%M:%S')
        tmp = [record.asctime, str(record.levelname), str(record.name)]
        s = self.format(record)
        if record.exc_info:
            # Cache the traceback text to avoid converting it multiple times
            # (it's constant anyway)
            if not record.exc_text:
                record.exc_text = logging.Formatter.formatException(self, record.exc_info)  # type: ignore  # noqa: E501
        if record.exc_text:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + record.exc_text
        if record.stack_info:
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + record.stack_info
        tmp.append(s)
        return tmp

    def enqueue(self, record: Any) -> None:
        """Enqueue a message prepared by :meth:`prepare`, if the fullname is given."""
        # TODO adjust serialization according to protocol definition
        try:
            self.queue.send_multipart((self.fullname.encode(), json.dumps(record).encode()))  # type: ignore  # noqa: E501
        except AttributeError:
            pass

    def close(self) -> None:
        self.queue.close(1)  # type: ignore
