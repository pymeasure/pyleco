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
import pickle
from typing import Any, Iterable, Optional, Union

import zmq

from ..core import PROXY_RECEIVING_PORT
from ..core.data_message import DataMessage, MessageTypes


class DataPublisher:
    """
    Publishing data via the LECO data protocol.

    :param str full_name: Name of the publishing Component
    :param str address: Address of the server, default is localhost.
    :param int port: Port of the server, defaults to 11100, default proxy.
    :param log: Logger to log to.

    Sending :class:`DataMessage` via the data protocol.

    Quantities may be expressed as a (magnitude number, units str) tuple.
    """

    full_name: str

    def __init__(
        self,
        full_name: str,
        host: str = "localhost",
        port: int = PROXY_RECEIVING_PORT,
        log: Optional[logging.Logger] = None,
        context: Optional[zmq.Context] = None,
        **kwargs,
    ) -> None:
        if log is None:
            self.log = logging.getLogger(f"{__name__}.Publisher")
        else:
            self.log = log.getChild("Publisher")
        self.log.info(f"Publisher started at {host}:{port}.")
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.PUB)
        self.socket.connect(f"tcp://{host}:{port}")
        self.full_name = full_name
        super().__init__(**kwargs)

    def __del__(self) -> None:
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        self.socket.close(1)

    def __call__(self, data: Any) -> None:
        """Publish `data`."""
        self.send_data(data=data)

    def send_message(self, message: DataMessage) -> None:
        """Send a data protocol message."""
        self.socket.send_multipart(message.to_frames())

    def send_data(
        self,
        data: Any,
        topic: Optional[Union[bytes, str]] = None,
        conversation_id: Optional[bytes] = None,
        message_type: Union[MessageTypes, int] = MessageTypes.NOT_DEFINED,
        additional_payload: Optional[Iterable[bytes]] = None,
    ) -> None:
        """Send the `data` via the data protocol."""
        message = DataMessage(
            topic=topic or self.full_name,
            data=data,
            conversation_id=conversation_id,
            message_type=message_type,
            additional_payload=additional_payload,
        )
        self.send_message(message)

    def send_legacy(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            # 234 is message type for legacy pickle: publish variable name as topic and pickle it
            self.send_data(topic=key, data=pickle.dumps(value), message_type=234)

    def set_full_name(self, full_name: str) -> None:
        """Set the full name of the data publisher.

        This method is useful for the listener's handler. That way a change of the listener's
        name or namespace is transferred easily to the publisher as well.

        .. code::

            listener = Listener()
            publisher = data_publisher(full_name=listener.full_name)
            listener.message_handler.register_on_name_change_method(publisher.set_full_name)

        """
        self.full_name = full_name
