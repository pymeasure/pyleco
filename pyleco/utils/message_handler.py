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
from functools import wraps
from json import JSONDecodeError
import logging
from typing import Any, Callable, Optional, Union, TypeVar

import zmq

from ..core import COORDINATOR_PORT
from ..core.leco_protocols import ExtendedComponentProtocol
from ..core.message import Message, MessageTypes
from ..core.serialization import JsonContentTypes, get_json_content_type
from ..json_utils.errors import JSONRPCError
from ..json_utils.rpc_generator import RPCGenerator
from ..json_utils.rpc_server import RPCServer
from .log_levels import PythonLogLevels
from .message_handler_base import MessageHandlerBase
from .zmq_log_handler import ZmqLogHandler



ReturnValue = TypeVar("ReturnValue")


class MessageHandler(MessageHandlerBase, ExtendedComponentProtocol):
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

    current_message: Message
    additional_response_payload: Optional[list[bytes]] = None

    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: int = COORDINATOR_PORT,
        protocol: str = "tcp",
        log: Optional[logging.Logger] = None,
        context: Optional[zmq.Context] = None,
        **kwargs,
    ):
        self.name = name
        self._namespace: Union[str, None] = None
        self._full_name: str = name
        self.rpc = RPCServer(title=name)
        self.rpc_generator = RPCGenerator()
        self.register_rpc_methods()

        self.setup_logging(log=log)
        self.setup_socket(
            host=host, port=port, protocol=protocol, context=context or zmq.Context.instance()
        )

        super().__init__(**kwargs)
        self.setup_message_buffer()

    @property
    def namespace(self) -> Union[str, None]:
        return self._namespace

    @namespace.setter
    def namespace(self, value: Union[str, None]) -> None:  # type: ignore
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

    def register_rpc_method(self, method: Callable[..., Any], **kwargs) -> None:
        """Register a method to be available via rpc calls."""
        self.rpc.method(**kwargs)(method)

    def _handle_binary_return_value(
        self, return_value: tuple[ReturnValue, list[bytes]]
    ) -> ReturnValue:
        self.additional_response_payload = return_value[1]
        return return_value[0]

    @staticmethod
    def _pass_through(return_value: ReturnValue) -> ReturnValue:
        return return_value

    def _generate_binary_capable_method(
        self,
        method: Callable[..., Union[ReturnValue, tuple[ReturnValue, list[bytes]]]],
        accept_binary_input: bool = False,
        return_binary_output: bool = False,
    ) -> Callable[..., ReturnValue]:
        returner = self._handle_binary_return_value if return_binary_output else self._pass_through
        if accept_binary_input is True:

            @wraps(method)
            def modified_method(*args, **kwargs) -> ReturnValue:  # type: ignore
                if args:
                    args_l = list(args)
                    if args_l[-1] is None:
                        args_l[-1] = self.current_message.payload[1:]
                    else:
                        args_l.append(self.current_message.payload[1:])
                    args = args_l  # type: ignore[assignment]
                else:
                    kwargs["additional_payload"] = self.current_message.payload[1:]
                return_value = method(
                    *args, **kwargs
                )
                return returner(return_value=return_value)  # type: ignore
        else:

            @wraps(method)
            def modified_method(*args, **kwargs) -> ReturnValue:
                return_value = method(*args, **kwargs)
                return returner(return_value=return_value)  # type: ignore

        doc_addition = (
            f"(binary{' input' * accept_binary_input}{' output' * return_binary_output} method)"
        )
        try:
            modified_method.__doc__ += "\n" + doc_addition  # type: ignore[operator]
        except TypeError:
            modified_method.__doc__ = doc_addition
        return modified_method  # type: ignore

    def register_binary_rpc_method(
        self,
        method: Callable[..., Union[Any, tuple[Any, list[bytes]]]],
        accept_binary_input: bool = False,
        return_binary_output: bool = False,
        **kwargs,
    ) -> None:
        """Register a method which accepts binary input and/or returns binary values.

        :param accept_binary_input: the method must accept the additional payload as an
            `additional_payload=None` parameter (default value must be present as `None`!).
        :param return_binary_output: the method must return a tuple of a JSON-able python object
            (e.g. `None`) and of a list of bytes objects, to be sent as additional payload.
        """
        modified_method = self._generate_binary_capable_method(
            method=method,
            accept_binary_input=accept_binary_input,
            return_binary_output=return_binary_output,
        )
        self.register_rpc_method(modified_method, **kwargs)

    def register_rpc_methods(self) -> None:
        """Register methods for RPC."""
        self.register_rpc_method(self.shut_down)
        self.register_rpc_method(self.set_log_level)
        self.register_rpc_method(self.pong)

    # Base communication
    def send(
        self,
        receiver: Union[bytes, str],
        conversation_id: Optional[bytes] = None,
        data: Optional[Any] = None,
        **kwargs,
    ) -> None:
        """Send a message to a receiver with serializable `data`."""
        try:
            super().send(receiver=receiver, conversation_id=conversation_id, data=data, **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            # TODO send an error message to the receiver?

    # Message handling in loop
    def handle_message(self, message: Message) -> None:
        if message.header_elements.message_type == MessageTypes.JSON:
            self.handle_json_message(message=message)
        else:
            self.handle_unknown_message_type(message=message)

    def handle_json_message(self, message: Message) -> None:
        try:
            data: dict[str, Any] = message.data  # type: ignore
        except JSONDecodeError as exc:
            self.log.exception(f"Could not decode json message {message}", exc_info=exc)
            return
        content = get_json_content_type(data)
        if JsonContentTypes.REQUEST in content:
            self.handle_json_request(message=message)
        elif JsonContentTypes.ERROR in content:
            self.handle_json_error(message=message)
        elif JsonContentTypes.RESULT in content:
            self.handle_json_result(message)
        else:
            self.log.error(f"Invalid JSON message received: {message}")

    def handle_json_request(self, message: Message) -> None:
        response = self.process_json_message(message=message)
        if response is not None:
            self.send_message(response)

    def process_json_message(self, message: Message) -> Optional[Message]:
        self.current_message = message
        self.additional_response_payload = None
        self.log.info(f"Handling commands of {message}.")
        reply = self.rpc.process_request(message.payload[0])
        if reply is None:
            return None
        else:
            response = Message(
                message.sender,
                conversation_id=message.conversation_id,
                message_type=MessageTypes.JSON,
                data=reply,
                additional_payload=self.additional_response_payload
            )
            return response

    def handle_json_error(self, message: Message) -> None:
        self.log.warning(f"Error message from {message.sender!r} received: {message}")

    def handle_json_result(self, message: Message) -> None:
        self.log.warning(f"Unsolicited message from {message.sender!r} received: '{message}'")

    def handle_unknown_message_type(self, message: Message) -> None:
        self.log.warning(
            f"Message from {message.sender!r} with unknown message type "
            f"{message.header_elements.message_type} received: '{message.data}', "
            f"{message.payload!r}."
        )

    # Methods offered via RPC
    def set_log_level(self, level: str) -> None:
        """Set the log level."""
        plevel = PythonLogLevels[level]
        self.root_logger.setLevel(plevel)

    def shut_down(self) -> None:
        self.stop_event.set()
