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
from typing import Any, Dict, List, Optional, Protocol, Tuple

# from jsonrpc2pyclient._irpcclient import IRPCClient
from openrpc import RPCServer
import zmq

from ..core.protocols import ExtendedComponent
from ..core.message import Message
from ..errors import NOT_SIGNED_IN, DUPLICATE_NAME
from ..core.rpc_generator import RPCGenerator
from .zmq_log_handler import ZmqLogHandler


# Parameters
heartbeat_interval = 10  # s


class Event(Protocol):
    """Check compatibility with threading.Event."""
    def is_set(self) -> bool: ...

    def set(self) -> None: ...


class InfiniteEvent(Event):
    """A simple Event if the one from `threading` module is not necessary."""
    def __init__(self):
        self._flag = False

    def is_set(self):
        return self._flag

    def set(self):
        self._flag = True


class MessageHandler(ExtendedComponent):
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

    def __init__(self, name: str, host: str = "localhost", port: int = 12300, protocol: str = "tcp",
                 log: Optional[logging.Logger] = None,
                 context=None,
                 **kwargs):
        self.name = name
        self.node: None | str = None
        self.full_name = name
        context = context or zmq.Context.instance()
        self.rpc = RPCServer(title=name)
        self.rpc_generator = RPCGenerator()
        self.publish_rpc_methods()

        if log is None:
            log = logging.getLogger("__main__")
        # Add the ZmqLogHandler to the root logger, unless it has already a Handler.
        first_pub_handler = True  # we expect to be the first ZmqLogHandler
        for h in log.handlers:
            if isinstance(h, ZmqLogHandler):
                first_pub_handler = False
                break
        if first_pub_handler:
            self.logHandler = ZmqLogHandler()
            log.addHandler(self.logHandler)
        self.root_logger = log
        self.log = self.root_logger.getChild("MessageHandler")

        # ZMQ setup
        self.socket = context.socket(zmq.DEALER)
        self.log.info(f"MessageHandler connecting to {host}:{port}")
        self.socket.connect(f"{protocol}://{host}:{port}")

        super().__init__(**kwargs)  # for cooperation

    def publish_rpc_methods(self) -> None:
        """Publish methods for RPC."""
        self.rpc.method(self.shutdown)
        self.rpc.method(self.set_log_level)
        self.rpc.method(self.pong)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        """Close the connection."""
        self.socket.close(1)

    # Base communication
    def sign_in(self) -> None:
        self._send_message(Message(
            receiver=b"COORDINATOR", data=self.rpc_generator.build_request_str(method="sign_in")))

    def heartbeat(self) -> None:
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self._send_message(Message(b"COORDINATOR"))

    def sign_out(self) -> None:
        self._send_message(Message(
            receiver=b"COORDINATOR", data=self.rpc_generator.build_request_str(method="sign_out")))

    def _send_message(self, message: Message) -> None:
        """Send a message, supplying sender information."""
        if not message.sender:
            message.sender = self.full_name.encode()
        frames = message.get_frames_list()
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _send(self, receiver: bytes | str, sender: bytes | str = b"", data: Optional[Any] = None,
              conversation_id: bytes = b"", **kwargs) -> None:
        """Compose and send a message to a `receiver` with serializable `data`."""
        try:
            message = Message(receiver=receiver, sender=sender, data=data,
                              conversation_id=conversation_id, **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            # TODO send an error message?
        else:
            self._send_message(message)

    # User commands, implements Communicator
    def send(self, receiver: bytes | str, data: Optional[Any] = None,
             conversation_id: bytes = b"", **kwargs) -> None:
        """Send a message to a receiver with serializable `data`."""
        self._send(receiver=receiver, data=data, conversation_id=conversation_id, **kwargs)

    def send_message(self, message: Message) -> None:
        self._send_message(message)

    # Continuous listening and message handling
    def listen(self, stop_event: Event = InfiniteEvent(), waiting_time: int = 100) -> None:
        """Listen for zmq communication until `stop_event` is set or until KeyboardInterrupt.

        :param stop_event: Event to stop the listening loop.
        :param waiting_time: Time to wait for a readout signal in ms.
        """
        self.log.info(f"Start to listen as '{self.name}'.")
        self.stop_event = stop_event
        # Prepare
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        # open communication
        self.sign_in()
        next_beat = time.perf_counter() + heartbeat_interval
        # Loop
        try:
            while not stop_event.is_set():
                socks = dict(poller.poll(waiting_time))
                if self.socket in socks:
                    self.handle_message()
                elif (now := time.perf_counter()) > next_beat:
                    self.heartbeat()
                    next_beat = now + heartbeat_interval
        except KeyboardInterrupt:
            pass  # User stops the loop
        except Exception:
            raise
        # Close
        self.log.info(f"Stop listen as '{self.name}'.")
        self.sign_out()
        self.handle_message()

    def handle_message(self) -> None:
        """Interpret incoming message.

        COORDINATOR messages are handled and then :meth:`handle_commands` does the rest.
        """
        msg = Message.from_frames(*self.socket.recv_multipart())
        self.log.debug(f"Handling {msg}")
        if not msg.payload:
            return
        if msg.sender_name == b"COORDINATOR" and isinstance(msg.data, dict):
            if self.node is None and msg.data.get("result", False) is None:
                # TODO additional check, that this is the answer to sign_in?
                self.finish_sign_in(msg)
                return
            elif (error := msg.data.get("error")):
                if error.get("code") == NOT_SIGNED_IN.code:
                    self.node = None
                    self.full_name = self.name
                    try:
                        del self.logHandler.fullname
                    except AttributeError:
                        pass  # already deleted.
                    self.sign_in()
                    self.log.warning("I was not signed in, signing in.")
                    return
                elif error.get("code") == DUPLICATE_NAME.code:
                    self.log.warning("Sign in failed, the name is already used.")
                    return
            # TODO what happens with a returned ping request?
        self.handle_commands(msg)

    def finish_sign_in(self, message: Message) -> None:
        self.node = message.sender_node.decode()
        self.full_name = ".".join((self.node, self.name))
        self.rpc.title = self.full_name
        try:
            self.logHandler.fullname = self.full_name
        except AttributeError:
            pass
        self.log.info(f"Signed in to Node '{self.node}'.")

    def handle_commands(self, msg: Message) -> None:
        """Handle the list of commands in the message."""
        if msg.payload and b'"jsonrpc":' in msg.payload[0]:
            if b'"method": ' in msg.payload[0]:
                self.log.info(f"Handling {msg}.")
                reply = self.rpc.process_request(msg.payload[0])
                response = Message(msg.sender, conversation_id=msg.conversation_id, data=reply)
                self.send_message(response)
            else:
                self.log.error(f"Unknown message from {msg.sender} received: {msg.payload[0]}")
        else:
            self.log.warning(f"Unknown message from {msg.sender} received: '{msg.data}', {msg.payload}.")

    def set_log_level(self, level: int) -> None:
        """Set the log level."""
        self.root_logger.setLevel(level)

    def shutdown(self) -> None:
        self.stop_event.set()


class BaseController(MessageHandler):
    """Control something, allow to get/set properties and call methods."""

    def publish_rpc_methods(self) -> None:
        super().publish_rpc_methods()
        self.rpc.method(self.get_properties)
        self.rpc.method(self.set_properties)
        self.rpc.method(self.call_method)

    def get_properties(self, properties: List[str] | Tuple[str, ...]) -> Dict[str, Any]:
        """Get properties from the list `properties`."""
        data = {}
        for key in properties:
            data[key] = v = getattr(self, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_properties(self, properties: Dict[str, Any]) -> None:
        """Set properties from a dictionary."""
        for key, value in properties.items():
            setattr(self, key, value)

    def call(self, method: str, args: list | tuple, kwargs: Dict[str, Any]) -> Any:
        """Call a method with arguments dictionary `kwargs`.

        Any method can be called, even if not setup as rpc call.
        It is preferred though, to add methods of your device with a rpc call.
        """
        # Deprecated
        return getattr(self, method)(*args, **kwargs)

    def call_method(self, method: str, _args: Optional[list | tuple] = None, **kwargs) -> Any:
        """Call a method with arguments dictionary `kwargs`.

        Any method can be called, even if not setup as rpc call.
        It is preferred though, to add methods of your device with a rpc call.
        """
        if _args is None:
            _args = ()
        return getattr(self, method)(*_args, **kwargs)
