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
import time
from typing import Any, Callable, Optional, Union

from openrpc import RPCServer
import zmq

from ..core import COORDINATOR_PORT
from ..core.leco_protocols import ExtendedComponentProtocol
from ..core.message import Message
from ..errors import NOT_SIGNED_IN, DUPLICATE_NAME
from ..core.rpc_generator import RPCGenerator
from ..core.serialization import generate_conversation_id
from .zmq_log_handler import ZmqLogHandler
from .events import Event, SimpleEvent


# Parameters
heartbeat_interval = 10  # s


class MessageHandler(ExtendedComponentProtocol):
    """Maintain connection to the Coordinator and listen to incoming messages.

    This class is inteded to run in a thread, maintain the connection to the coordinator
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
    namespace: None | str

    def __init__(self, name: str,
                 host: str = "localhost", port: int = COORDINATOR_PORT, protocol: str = "tcp",
                 log: Optional[logging.Logger] = None,
                 context: Optional[zmq.Context] = None,
                 **kwargs):
        self.name = name
        self.namespace: None | str = None
        self.full_name = name
        context = context or zmq.Context.instance()
        self.rpc = RPCServer(title=name)
        self.rpc_generator = RPCGenerator()
        self.register_rpc_methods()

        self._requests: dict[bytes, str] = {}
        self.response_methods: dict[str, Callable] = {
            "sign_in": self.handle_sign_in,
            "sign_out": self.handle_sign_out
        }

        if log is None:
            log = logging.getLogger("__main__")
        # Add the ZmqLogHandler to the root logger, unless it has already a Handler.
        first_pub_handler = True  # we expect to be the first ZmqLogHandler
        for h in log.handlers:
            if isinstance(h, ZmqLogHandler):
                first_pub_handler = False
                self.logHandler = h
                break
        if first_pub_handler:
            self.logHandler = ZmqLogHandler()
            log.addHandler(self.logHandler)
        self.root_logger = log
        self.log = self.root_logger.getChild("MessageHandler")

        # ZMQ setup
        self.socket: zmq.Socket = context.socket(zmq.DEALER)
        self.log.info(f"MessageHandler connecting to {host}:{port}")
        self.socket.connect(f"{protocol}://{host}:{port}")

        super().__init__(**kwargs)  # for cooperation

    def register_rpc_methods(self) -> None:
        """Publish methods for RPC."""
        self.rpc.method()(self.shut_down)
        self.rpc.method()(self.set_log_level)
        self.rpc.method()(self.pong)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection."""
        self.socket.close(1)

    # Base communication
    def sign_in(self) -> None:
        self._ask_rpc_async(b"COORDINATOR", method="sign_in")

    def heartbeat(self) -> None:
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self._send_message(Message(b"COORDINATOR"))

    def sign_out(self) -> None:
        self._ask_rpc_async(b"COORDINATOR", method="sign_out")

    def _send_message(self, message: Message) -> None:
        """Send a message, supplying sender information."""
        if not message.sender:
            message.sender = self.full_name.encode()
        frames = message.to_frames()
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _send(self, receiver: bytes | str, sender: bytes | str = b"", data: Optional[Any] = None,
              conversation_id: Optional[bytes] = None, **kwargs) -> None:
        """Compose and send a message to a `receiver` with serializable `data`."""
        try:
            message = Message(receiver=receiver, sender=sender, data=data,
                              conversation_id=conversation_id, **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            # TODO send an error message?
        else:
            self._send_message(message)

    def _ask_rpc_async(self, receiver: bytes | str, method: str, **kwargs) -> None:
        """Send a message and store the converation_id."""
        cid = generate_conversation_id()
        message = Message(receiver=receiver, conversation_id=cid,
                          data=self.rpc_generator.build_request_str(method=method, **kwargs))
        self._requests[cid] = method
        self._send_message(message)

    # User commands, implements Communicator
    def send(self, receiver: bytes | str, data: Optional[Any] = None,
             conversation_id: Optional[bytes] = None, **kwargs) -> None:
        """Send a message to a receiver with serializable `data`."""
        self._send(receiver=receiver, data=data, conversation_id=conversation_id, **kwargs)

    def send_message(self, message: Message) -> None:
        self._send_message(message)

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
        except Exception:
            raise
        # Close
        self._listen_close()

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

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: int | None
                             ) -> dict[zmq.Socket, int]:
        """Check the socks for incoming messages and handle them.

        :param waiting_time: Timeout of the poller in ms.
        """
        socks = dict(poller.poll(waiting_time))
        if self.socket in socks:
            self.handle_message()
            del socks[self.socket]
        elif (now := time.perf_counter()) > self.next_beat:
            self.heartbeat()
            self.next_beat = now + heartbeat_interval
        return socks

    def _listen_close(self) -> None:
        """Close the listening loop."""
        self.log.info(f"Stop listen as '{self.name}'.")
        self.sign_out()
        self.handle_message()

    def handle_message(self) -> None:
        """Interpret incoming message.

        COORDINATOR messages are handled and then :meth:`handle_commands` does the rest.
        """
        msg = Message.from_frames(*self.socket.recv_multipart())
        self.log.debug(f"Handling message {msg}")
        if not msg.payload:
            return
        try:
            if (msg.sender_elements.name == b"COORDINATOR"
                    and (error := msg.data.get("error"))  # type: ignore
                    and error.get("code") == NOT_SIGNED_IN.code):
                self.namespace = None
                self.set_full_name(self.name)
                self.sign_in()
                self.log.warning("I was not signed in, signing in.")
                return
            elif (method := self._requests.get(msg.conversation_id)):
                self.handle_response(msg, method)
                return
        except AttributeError as exc:
            self.log.exception(f"Message data {msg.data} misses an attribute!", exc_info=exc)
        else:
            self.handle_commands(msg)

    def handle_response(self, message: Message, method: str):
        del self._requests[message.conversation_id]
        self.response_methods[method](message)

    def handle_sign_in(self, message: Message) -> None:
        if not isinstance(message.data, dict):
            self.log.error(f"Not json message received: {message}")
            return
        if message.data.get("result", False) is None:
            self.finish_sign_in(message)
        elif (error := message.data.get("error")):
            if error.get("code") == DUPLICATE_NAME.code:
                self.log.warning("Sign in failed, the name is already used.")
                return

    def handle_sign_out(self, message: Message) -> None:
        if isinstance(message.data, dict) and message.data.get("result", False) is None:
            self.finish_sign_out(message)
        else:
            self.log.error(f"Signing out failed with {message}.")

    def finish_sign_in(self, message: Message) -> None:
        self.namespace = message.sender_elements.namespace.decode()
        self.set_full_name(full_name=".".join((self.namespace, self.name)))
        self.log.info(f"Signed in to Node '{self.namespace}'.")

    def finish_sign_out(self, message: Message) -> None:
        self.namespace = None
        self.set_full_name(full_name=self.name)
        self.log.info(f"Signed out from Node '{message.sender_elements.namespace.decode()}'.")

    def set_full_name(self, full_name: str) -> None:
        self.full_name = full_name
        self.rpc.title = full_name
        self.logHandler.fullname = self.full_name

    def handle_commands(self, msg: Message) -> None:
        """Handle the list of commands in the message."""
        if msg.payload and b'"jsonrpc":' in msg.payload[0]:
            if b'"method":' in msg.payload[0]:
                self.log.info(f"Handling commands of  {msg}.")
                reply = self.rpc.process_request(msg.payload[0])
                response = Message(msg.sender, conversation_id=msg.conversation_id, data=reply)
                self.send_message(response)
            else:
                self.log.error(f"Unknown message from {msg.sender!r} received: {msg.payload[0]!r}")
        else:
            self.log.warning(f"Unknown message from {msg.sender!r} received: '{msg.data}', {msg.payload!r}.")  # noqa: E501

    def set_log_level(self, level: int) -> None:
        """Set the log level."""
        self.root_logger.setLevel(level)

    def shut_down(self) -> None:
        self.stop_event.set()


class BaseController(MessageHandler):
    """Control something, allow to get/set properties and call methods."""

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method()(self.get_parameters)
        self.rpc.method()(self.set_parameters)
        self.rpc.method()(self.call_action)

    def get_parameters(self, parameters: Union[list[str], tuple[str, ...]]) -> dict[str, Any]:
        data = {}
        for key in parameters:
            data[key] = v = getattr(self, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        for key, value in parameters.items():
            setattr(self, key, value)

    def call_action(self, action: str, args: Optional[Union[list, tuple]] = None,
                    kwargs: Optional[dict[str, Any]] = None) -> Any:
        """Call an action with positional arguments ``args`` and keyword arguments ``kwargs``.

        Any action can be called, even if not setup as rpc call.
        It is preferred though, to add methods of your device with a rpc call.
        """
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        return getattr(self, action)(*args, **kwargs)
