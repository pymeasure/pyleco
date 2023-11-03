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
from threading import Thread, Event
from time import sleep
from typing import Any, Optional, Union

import zmq

from ..core import PROXY_SENDING_PORT, COORDINATOR_PORT
from .extended_message_handler import ExtendedMessageHandler
from .publisher import Publisher
from .pipe_handler import PipeHandler, CommunicatorPipe
from ..core.message import Message, MessageTypes
from ..core.serialization import generate_conversation_id
from ..core.rpc_generator import RPCGenerator
from ..core.internal_protocols import CommunicatorProtocol


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Listener(CommunicatorProtocol):
    """Listening on published data and opening a configuration port, both in a separate thread.

    It works on one side like a :class:`Communicator`, offering communication to the network,
    and on the other side handles simultaneously incoming messages.
    For that reason, the main part is in a separate thread.

    Call :meth:`.start_listen()` to actually listen.

    :param name: Name to listen under for control commands.
    :param int data_port: Port number for the data protocol.
    :param heartbeat_interval: Interval between two heartbeats in s.
    :param context: zmq context.
    :param logger: Logger instance whose logs should be published. Defaults to "__main__".
    """

    def __init__(self,
                 name: str,
                 host: str = "localhost",
                 port: int = COORDINATOR_PORT,
                 data_host: str | None = None,
                 data_port: int = PROXY_SENDING_PORT,
                 logger: Optional[logging.Logger] = None,
                 dataPort: int | None = None,  # deprecated
                 timeout: float = 1,
                 **kwargs) -> None:
        super().__init__(**kwargs)
        log.info(f"Start Listener for '{name}'.")

        # deprecated entries
        if dataPort is not None:
            data_port = dataPort

        self._name = name
        self.logger = logger
        self.timeout = timeout

        self.rpc_generator = RPCGenerator()

        self.coordinator_address = host, port
        self.data_address = data_host or host, data_port

    def close(self) -> None:
        """Close everything."""
        self.stop_listen()

    @property
    def name(self) -> str:
        return self.communicator.name

    @name.setter
    def name(self, value: str) -> None:
        self.communicator.name = value

    @property
    def namespace(self) -> str | None:  # type: ignore[override]  # only the handler sets namespace.
        return self.communicator.namespace

    @property
    def full_name(self) -> str:
        return self.communicator.full_name

    # Methods to control the Listener
    def stop_listen(self) -> None:
        """Stop the listener Thread."""
        try:
            if self.thread.is_alive():
                log.debug("Stopping listener thread.")
                self.stop_event.set()
                self.thread.join()
                self.communicator.close()
                log.removeHandler(self.message_handler.logHandler)
                if self.logger is not None:
                    self.logger.removeHandler(self.message_handler.logHandler)
        except AttributeError:
            pass

    #   Control protocol
    def send(self, receiver: bytes | str, conversation_id: Optional[bytes] = None,
             data: Optional[Any] = None,
             **kwargs) -> None:
        """Send a message via control protocol."""
        message = Message(receiver=receiver, conversation_id=conversation_id,
                          data=data, **kwargs)
        self.send_message(message)

    def send_message(self, message: Message) -> None:
        self.communicator.send_message(message=message)

    def reply(self, header: list, content: object) -> None:
        """Send a reply according to the original header frames and a content frame."""
        sender, conversation_id = header
        self.send(receiver=sender, conversation_id=conversation_id, data=content)

    def read_answer(self, conversation_id: bytes, tries: int = 1,
                    timeout: float = 1) -> tuple[str, str, bytes, bytes, object]:
        """Read the answer of the original message with `conversation_id`."""
        # TODO deprecated?
        msg = self.read_answer_as_message(conversation_id=conversation_id, timeout=timeout)
        return self._turn_message_to_list(msg=msg)

    @staticmethod
    def _turn_message_to_list(msg: Message) -> tuple[str, str, bytes, bytes, object]:
        """Turn a message into a list of often used parameters.

        :return: receiver, sender, conversation_id, message_id, data
        """
        # adding an empty byte for a faked message_id.
        return (msg.receiver.decode(), msg.sender.decode(), msg.conversation_id, b"",
                msg.data)

    def read_answer_as_message(self, conversation_id: bytes, tries: int = 1,
                               timeout: float = 1) -> Message:
        return self.communicator.read_message(conversation_id=conversation_id)

    def ask(self, receiver: bytes | str, conversation_id: Optional[bytes] = None, data=None,
            **kwargs) -> Message:
        if conversation_id is None:
            conversation_id = generate_conversation_id()
        if isinstance(receiver, str):
            receiver = receiver.encode()
        message = Message(receiver=receiver, conversation_id=conversation_id, data=data, **kwargs)
        return self.ask_message(message=message)

    def ask_message(self, message: Message) -> Message:
        return self.communicator.ask_message(message=message)

    def ask_rpc(self, receiver: bytes | str, method: str, **kwargs):
        string = self.rpc_generator.build_request_str(method=method, **kwargs)
        response = self.ask(receiver=receiver, data=string, message_type=MessageTypes.JSON)
        return self.rpc_generator.get_result_from_response(response.payload[0])

    #   Data protocol
    def subscribe(self, topics: Union[str, list[str], tuple[str, ...]]) -> None:
        """Subscribe to a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self.communicator.subscribe(topic)
        else:
            self.communicator.subscribe(topics)

    def unsubscribe(self, topics: Union[str, list[str], tuple[str, ...]]) -> None:
        """Unsubscribe from a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self.communicator.unsubscribe(topic)
        else:
            self.communicator.unsubscribe(topics)

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all subscriptions."""
        self.communicator.unsubscribe_all()

    # Generic
    def rename(self, new_name: str) -> None:
        """Rename the listener to `new_name`."""
        self.communicator.name = new_name

    def sign_in(self) -> None:
        return  # already handled in the message_handler

    def sign_out(self) -> None:
        return  # already handled in the message_handler

    def start_listen(self, data_host: Optional[str] = None, data_port: Optional[int] = None
                     ) -> None:
        """Start to listen in a thread.

        :param str host: Host name to listen to.
        :param int dataPort: Port for the subscription.
        """
        coordinator_host, coordinator_port = self.coordinator_address
        self.stop_listen()
        self.stop_event = Event()
        self.thread = Thread(
            target=self._listen,
            args=(
                self._name,
                self.stop_event,
                coordinator_host,
                coordinator_port,
                data_host or self.data_address[0],
                data_port or self.data_address[1],
            ))
        self.thread.daemon = True
        self.thread.start()
        for _ in range(10):
            sleep(0.05)
            try:
                self.communicator: CommunicatorPipe = self.message_handler.get_communicator()
                log.addHandler(self.message_handler.logHandler)
                self.rpc = self.message_handler.rpc
                if self.logger is not None:
                    self.logger.addHandler(self.message_handler.logHandler)
            except AttributeError:
                pass
            else:
                break

    def get_communicator(self) -> CommunicatorPipe:
        return self.message_handler.get_communicator()

    """
    Methods below are executed in the thread, DO NOT CALL DIRECTLY!
    """

    def _listen(self, name: str, stop_event: Event, coordinator_host: str, coordinator_port: int,
                data_host: str, data_port: int) -> None:
        self.message_handler = PipeHandler(name, host=coordinator_host, port=coordinator_port)
        self.message_handler.listen(stop_event=stop_event, host=data_host, data_port=data_port)


class Republisher(ExtendedMessageHandler):
    """Listen on some values and republish a modified version.

    Call `listener.start_listen()` to actually listen.

    Republish values under a new name after having modified them.
    Time delay is around 1-2 ms.

    :param dict handlings: Dictionary with tuples of callable and new name.

    The following example takes the values of key 'old' and publishes the square
    of that value under the key 'new'. Wait until a KeyboardInterrupt (Ctrl+C) happens.

    .. code-block:: python

        def square(value):
            return value ** 2
        republisher = Republisher(handlings={'old': (square, "new")})
        republisher.start_listen()
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
    """

    def __init__(self, name: str = "Republisher", handlings: Optional[dict] = None,
                 *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.publisher = Publisher()
        self.handlings = {} if handlings is None else handlings

    def start_listen(self, host: str = "localhost", data_port: int = PROXY_SENDING_PORT,
                     stop_event: Event | None = None,
                     **kwargs) -> None:
        if stop_event is None:
            self.listen(host=host, data_port=data_port)
        else:
            self.listen(host=host, data_port=data_port, stop_event=stop_event)

    def _listen_setup(self, host: str = "localhost", data_port: int = PROXY_SENDING_PORT,
                      **kwargs) -> zmq.Poller:
        poller = super()._listen_setup(host, data_port, **kwargs)
        for key in self.handlings.keys():
            self.subscribe(key)
        return poller

    def handle_subscription_data(self, data: dict) -> None:
        """Call a calibration method and publish data under a new name."""
        new = {}
        if not isinstance(data, dict):
            log.error(f"{data} received, which is not a dictionary.")
        for key, value in data.items():
            if handling := self.handlings.get(key):
                try:
                    new[handling[1]] = handling[0](value)
                except Exception:
                    log.exception(f"Handling of '{key}' failed.")
        if new:
            self.publisher(new)
