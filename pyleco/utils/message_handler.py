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

import logging
import time
from typing import Any, Callable, Optional, Union

from jsonrpcobjects.errors import JSONRPCError
from openrpc import RPCServer
import zmq

from ..core import COORDINATOR_PORT
from ..core.leco_protocols import ExtendedComponentProtocol
from ..core.internal_protocols import CommunicatorProtocol
from ..core.message import Message, MessageTypes
from ..errors import NOT_SIGNED_IN, DUPLICATE_NAME
from ..core.rpc_generator import RPCGenerator
from .log_levels import PythonLogLevels
from .zmq_log_handler import ZmqLogHandler
from .events import Event, SimpleEvent


# Parameters
heartbeat_interval = 10  # s


class MessageHandler(CommunicatorProtocol, ExtendedComponentProtocol):
    """Maintain connection to the Coordinator and listen to incoming messages.

    This class is intended to run in a thread, maintain the connection to the coordinator
    with heartbeats and timely responses. If a message arrives which is not connected to the control
    protocol itself (e.g. ping message), another method is called.
    You may subclass this class in order to handle these messages as desired.

    You may use it as a context manager.

    :param str name: Name to listen to and to publish values with.
    :param str host: Host name (or IP address) of the Coordinator to connect to.
    :param int port: Port number of the Coordinator to connect to.
    :param protocol: Connection protocol.
    :param log: Logger instance whose logs should be published. Defaults to `getLogger("__main__")`.
    """
    name: str

    def __init__(self, name: str,
                 host: str = "localhost", port: int = COORDINATOR_PORT, protocol: str = "tcp",
                 log: Optional[logging.Logger] = None,
                 context: Optional[zmq.Context] = None,
                 **kwargs):
        self.name = name
        self._namespace: Union[str, None] = None
        self._full_name: str = name
        self._message_buffer: list[Message] = []
        self._requested_ids: set[bytes] = set()
        self.rpc = RPCServer(title=name)
        self.rpc_generator = RPCGenerator()
        self.register_rpc_methods()

        self.setup_logging(log=log)
        self.setup_socket(host=host, port=port, protocol=protocol,
                          context=context or zmq.Context.instance())

        super().__init__(**kwargs)

    @property
    def namespace(self) -> Union[str, None]:
        return self._namespace

    @namespace.setter
    def namespace(self, value: Union[str, None]) -> None:
        self._namespace = value
        full_name = self.name if value is None else ".".join((value, self.name))
        self.set_full_name(full_name=full_name)

    def set_full_name(self, full_name: str) -> None:
        self._full_name = full_name
        self.rpc.title = full_name
        self.log_handler.full_name = full_name

    @property
    def full_name(self) -> str:
        return self._full_name

    def setup_logging(self, log):
        if log is None:
            log = logging.getLogger("__main__")
        # Add the ZmqLogHandler to the root logger, unless it has already a Handler.
        first_pub_handler = True  # we expect to be the first ZmqLogHandler
        for h in log.handlers:
            if isinstance(h, ZmqLogHandler):
                first_pub_handler = False
                self.log_handler = h
                break
        if first_pub_handler:
            self.log_handler = ZmqLogHandler()
            log.addHandler(self.log_handler)
        self.root_logger = log
        self.log = self.root_logger.getChild("MessageHandler")  # for cooperation

    def setup_socket(self, host: str, port: int, protocol: str, context: zmq.Context) -> None:
        self.socket: zmq.Socket = context.socket(zmq.DEALER)
        self.log.info(f"MessageHandler connecting to {host}:{port}")
        self.socket.connect(f"{protocol}://{host}:{port}")

    def register_rpc_method(self, method: Callable, **kwargs) -> None:
        """Register a method to be available via rpc calls."""
        self.rpc.method(**kwargs)(method)

    def register_rpc_methods(self) -> None:
        """Register methods for RPC."""
        self.register_rpc_method(self.shut_down)
        self.register_rpc_method(self.set_log_level)
        self.register_rpc_method(self.pong)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection."""
        self.socket.close(1)

    # Base communication
    def sign_in(self) -> None:
        string = self.rpc_generator.build_request_str(method="sign_in")
        try:
            msg = self.ask(b"COORDINATOR", data=string, message_type=MessageTypes.JSON)
        except JSONRPCError as exc:
            json_error = exc.rpc_error
            if json_error.code == DUPLICATE_NAME.code:
                self.log.warning("Sign in failed, the name is already used.")
            else:
                self.log.warning(f"Sign in failed, unknown error '{json_error}'.")
        except TimeoutError:
            self.log.error("Signing in timed out.")
        else:
            self.finish_sign_in(msg)

    def heartbeat(self) -> None:
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self._send_message(Message(b"COORDINATOR"))

    def sign_out(self) -> None:
        try:
            self.ask_rpc(b"COORDINATOR", method="sign_out")
        except TimeoutError:
            self.log.warning("Waiting for sign out response timed out.")
        except Exception as exc:
            self.log.exception("Signing out failed.", exc_info=exc)
        else:
            self.finish_sign_out()

    def _send_message(self, message: Message) -> None:
        """Send a message, supplying sender information."""
        if not message.sender:
            message.sender = self.full_name.encode()
        frames = message.to_frames()
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _send(self, receiver: Union[bytes, str], sender: Union[bytes, str] = b"",
              data: Optional[Any] = None,
              conversation_id: Optional[bytes] = None, **kwargs) -> None:
        """Compose and send a message to a `receiver` with serializable `data`."""
        try:
            message = Message(receiver=receiver, sender=sender, data=data,
                              conversation_id=conversation_id, **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            # TODO send an error message to the receiver?
        else:
            self._send_message(message)

    def send(self,
             receiver: Union[bytes, str],
             conversation_id: Optional[bytes] = None,
             data: Optional[Any] = None,
             **kwargs) -> None:
        """Send a message to a receiver with serializable `data`."""
        self._send(receiver=receiver, data=data, conversation_id=conversation_id, **kwargs)

    def send_message(self, message: Message) -> None:
        self._send_message(message)

    def _read_socket_message(self, timeout: Optional[float] = None) -> Message:
        if self.socket.poll(int(timeout or self.timeout * 1000)):
            return Message.from_frames(*self.socket.recv_multipart())
        raise TimeoutError("Reading timed out")

    def _read_message(self, conversation_id: Optional[bytes] = None, timeout: Optional[float] = None
                      ) -> Message:
        if self._message_buffer:
            for i, msg in enumerate(self._message_buffer):
                cid = msg.conversation_id
                if conversation_id == cid:
                    self._requested_ids.discard(cid)
                    return self._message_buffer.pop(i)
                elif cid not in self._requested_ids and conversation_id is None:
                    return self._message_buffer.pop(i)
        stop = time.perf_counter() + (timeout or self.timeout)
        while True:
            msg = self._read_socket_message(timeout)
            cid = msg.conversation_id
            if conversation_id == cid:
                self._requested_ids.discard(cid)
                return msg
            elif conversation_id is not None or cid in self._requested_ids:
                self._message_buffer.append(msg)
            else:
                return msg
            if time.perf_counter() > stop:
                # inside the loop to do it at least once, even if timeout is 0
                break
        raise TimeoutError("Message not found.")

    def read_message(self, conversation_id: Optional[bytes] = None, timeout: Optional[float] = None
                     ) -> Message:
        msg = self._read_message(conversation_id=conversation_id, timeout=timeout)
        if msg.sender_elements.name == b"COORDINATOR" and msg.payload:
            try:
                self.rpc_generator.get_result_from_response(msg.payload[0])
            except JSONRPCError as exc:
                code = exc.rpc_error.code
                if code == NOT_SIGNED_IN.code:
                    self.handle_not_signed_in()
                raise
        return msg

    def ask_message(self, message: Message, timeout: Optional[float] = None
                    ) -> Message:
        self.send_message(message)
        cid = message.conversation_id
        # self._requested_ids.add(cid)
        return self.read_message(conversation_id=cid, timeout=timeout)

    # Continuous listening and message handling
    def listen(self, stop_event: Event = SimpleEvent(), waiting_time: int = 100, **kwargs) -> None:
        """Listen for zmq communication until `stop_event` is set or until KeyboardInterrupt.

        :param stop_event: Event to stop the listening loop.
        :param waiting_time: Time to wait for a readout signal in ms.
        """
        self.stop_event = stop_event
        poller = self._listen_setup(**kwargs)
        # Loop
        try:
            while not stop_event.is_set():
                self._listen_loop_element(poller=poller, waiting_time=waiting_time)
        except KeyboardInterrupt:
            pass  # User stops the loop
        finally:
            # Close
            self._listen_close(waiting_time=waiting_time)

    def _listen_setup(self) -> zmq.Poller:
        """Setup for listening.

        If you add your own sockets, remember to poll only for incoming messages.
        """
        self.log.info(f"Start to listen as '{self.name}'.")
        # Prepare
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        # open communication
        self.sign_in()
        self.next_beat = time.perf_counter() + heartbeat_interval
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: Optional[int]
                             ) -> dict[zmq.Socket, int]:
        """Check the socks for incoming messages and handle them.

        :param waiting_time: Timeout of the poller in ms.
        """
        socks = dict(poller.poll(waiting_time))
        if self.socket in socks:
            self.read_and_handle_message()
            del socks[self.socket]
        elif (now := time.perf_counter()) > self.next_beat:
            self.heartbeat()
            self.next_beat = now + heartbeat_interval
        return socks

    def _listen_close(self, waiting_time: Optional[int] = None) -> None:
        """Close the listening loop."""
        self.log.info(f"Stop listen as '{self.name}'.")
        self.sign_out()

    def read_and_handle_message(self) -> None:
        """Interpret incoming message, which have not been requested.
        """
        try:
            msg = self.read_message(timeout=0)
        except (TimeoutError, JSONRPCError):
            # only responses / errors arrived.
            return
        self.log.debug(f"Handling message {msg}")
        if not msg.payload:
            return  # no payload, that means just a heartbeat
        self.handle_commands(msg)

    def handle_not_signed_in(self) -> None:
        self.namespace = None
        self.sign_in()
        self.log.warning("I was not signed in, signing in.")

    def finish_sign_in(self, message: Message) -> None:
        self.namespace = message.sender_elements.namespace.decode()
        self.log.info(f"Signed in to Node '{self.namespace}'.")

    def finish_sign_out(self) -> None:
        self.log.info(f"Signed out from Node '{self.namespace}'.")
        self.namespace = None

    def handle_commands(self, msg: Message) -> None:
        """Handle the list of commands in the message."""
        if msg.header_elements.message_type == MessageTypes.JSON:
            if b'"method":' in msg.payload[0]:
                self.log.info(f"Handling commands of {msg}.")
                reply = self.rpc.process_request(msg.payload[0])
                response = Message(msg.sender, conversation_id=msg.conversation_id,
                                   message_type=MessageTypes.JSON, data=reply)
                self.send_message(response)
            else:
                self.log.error(f"Unknown message from {msg.sender!r} received: {msg.payload[0]!r}")
        else:
            self.log.warning(f"Message from {msg.sender!r} with unknown message type {msg.header_elements.message_type} received: '{msg.data}', {msg.payload!r}.")  # noqa: E501

    def set_log_level(self, level: str) -> None:
        """Set the log level."""
        plevel = PythonLogLevels[level]
        self.root_logger.setLevel(plevel)

    def shut_down(self) -> None:
        self.stop_event.set()
