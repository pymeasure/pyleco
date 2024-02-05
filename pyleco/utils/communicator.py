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
from time import perf_counter
from typing import Callable, Optional, Protocol, Union
from warnings import warn

from jsonrpcobjects.errors import JSONRPCError
import zmq

from ..core import COORDINATOR_PORT
from ..core.internal_protocols import CommunicatorProtocol
from ..core.message import Message, MessageTypes
from ..core.rpc_generator import RPCGenerator
from ..errors import DUPLICATE_NAME, NOT_SIGNED_IN


class BaseCommunicator(CommunicatorProtocol, Protocol):
    """Abstract class of a Communicator

    This class contains some logic, useful for users of the CommunicatorProtocol.
    """

    _message_buffer: list[Message]
    _requested_ids: set[bytes]
    log: logging.Logger
    namespace: Optional[str]

    # Methods required
    def _send_socket_message(self, message: Message) -> None: ...  # pragma: no cover

    def _read_socket_message(self, timeout: Optional[float] = None
                             ) -> Message: ...  # pragma: no cover

    # Context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    # Base communication
    def send_message(self, message: Message) -> None:
        """Send a message, supplying sender information."""
        if not message.sender:
            message.sender = self.full_name.encode()
        self.log.debug(f"Sending {message}")
        self._send_socket_message(message=message)

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

    def finish_sign_in(self, response_message: Message) -> None:
        self.namespace = response_message.sender_elements.namespace.decode()
        self.log.info(f"Signed in to Node '{self.namespace}'.")

    def heartbeat(self) -> None:
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self.send_message(Message(b"COORDINATOR"))

    def sign_out(self) -> None:
        try:
            self.ask_rpc(b"COORDINATOR", method="sign_out")
        except TimeoutError:
            self.log.warning("Waiting for sign out response timed out.")
        except Exception as exc:
            self.log.exception("Signing out failed.", exc_info=exc)
        else:
            self.finish_sign_out()

    def finish_sign_out(self) -> None:
        self.log.info(f"Signed out from Node '{self.namespace}'.")
        self.namespace = None

    # Reading messages with buffer
    def _find_buffer_message(self, conversation_id: Optional[bytes] = None) -> Optional[Message]:
        """Find a message in the buffer."""
        for i, msg in enumerate(self._message_buffer):
            cid = msg.conversation_id
            if conversation_id == cid:
                self._requested_ids.discard(cid)
                return self._message_buffer.pop(i)
            elif cid not in self._requested_ids and conversation_id is None:
                return self._message_buffer.pop(i)
        return None

    def _find_socket_message(self, conversation_id: Optional[bytes] = None,
                             timeout: Optional[float] = None,
                             ) -> Message:
        """Find a specific message among socket messages, storing the other ones in the buffer.

        :param conversation_id: Conversation ID to filter for, or next free message if None.
        """
        stop = perf_counter() + (timeout or self.timeout)
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
            if perf_counter() > stop:
                # inside the loop to do it at least once, even if timeout is 0
                break
        raise TimeoutError("Message not found.")

    def read_message(self, conversation_id: Optional[bytes] = None, timeout: Optional[float] = None,
                     ) -> Message:
        message = self._find_buffer_message(conversation_id=conversation_id)
        if message is None:
            message = self._find_socket_message(conversation_id=conversation_id, timeout=timeout)
        if message.sender_elements.name == b"COORDINATOR" and message.payload:
            try:
                self.rpc_generator.get_result_from_response(message.payload[0])
            except JSONRPCError as exc:
                code = exc.rpc_error.code
                if code == NOT_SIGNED_IN.code:
                    self.handle_not_signed_in()
                raise
        return message

    def handle_not_signed_in(self) -> None:
        self.namespace = None
        self.sign_in()
        self.log.warning("I was not signed in, signing in.")

    def ask_message(self, message: Message, timeout: Optional[float] = None) -> Message:
        self.send_message(message=message)
        return self.read_message(conversation_id=message.conversation_id, timeout=timeout)


class Communicator(BaseCommunicator):
    """A simple Communicator, which sends requests and reads the answer.

    This Communicator does not listen for incoming messages. It only handles messages, whenever
    you try to read one. It is intended for sending messages and reading the answer without
    implementing threading.

    The communicator can be used in a context, which ensures sign-in and sign-out:

    .. code::

        with Communicator(name="test") as com:
            com.send("receiver")

    :param str host: Hostname
    :param int port: Port to connect to.
    :param str name: Name to send messages as.
    :param int timeout: Timeout in s.
    :param bool auto_open: Open automatically a connection upon instantiation.
    :param str protocol: Protocol name to use.
    :param bool standalone: Whether to bind to the port in standalone mode.
    """

    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Optional[int] = COORDINATOR_PORT,
        timeout: float = 0.1,
        auto_open: bool = True,
        protocol: str = "tcp",
        standalone: bool = False,
        **kwargs,
    ) -> None:
        self.log = logging.getLogger(f"{__name__}.Communicator")
        self.host = host
        self.port = port
        self._conn_details = protocol, standalone
        self.timeout = timeout
        self.log.info(f"Communicator initialized on {host}:{port}.")
        if auto_open:
            self.open()
        self.name = name
        self.namespace = None
        self._message_buffer: list[Message] = []
        self._requested_ids: set[bytes] = set()
        self._last_beat: float = 0
        self._reading: Optional[Callable[[], list[bytes]]] = None
        self.rpc_generator = RPCGenerator()
        super().__init__(**kwargs)

    def open(self, context: Optional[zmq.Context] = None) -> None:
        """Open the connection."""
        context = context or zmq.Context.instance()
        self.connection: zmq.Socket = context.socket(zmq.DEALER)
        protocol, standalone = self._conn_details
        if standalone:
            self.connection.bind(f"{protocol}://*:{self.port}")
        else:
            self.connection.connect(f"{protocol}://{self.host}:{self.port}")

    def close(self) -> None:
        """Close the connection."""
        if (not hasattr(self, "connection")) or self.connection.closed:
            return
        try:
            self.sign_out()
        except TimeoutError:
            self.log.warning("Closing, the sign out failed with a timeout.")
        except ConnectionRefusedError:
            self.log.warning("Closing, the sign out failed with a refused connection.")
        finally:
            self.connection.close(1)

    def reset(self) -> None:
        """Reset socket"""
        self.close()
        self.open()

    def __del__(self) -> None:
        self.close()

    def __enter__(self):  # -> typing.Self for py>=3.11
        """Called with `with` keyword, returns the Director."""
        if not hasattr(self, "connection"):
            self.open()
        self.sign_in()
        return self

    def send_message(self, message: Message) -> None:
        now = perf_counter()
        if now > self._last_beat + 15 and message.payload and b"sign_in" not in message.payload[0]:
            self.sign_in()
        self._last_beat = now
        super().send_message(message=message)

    def _send_socket_message(self, message: Message) -> None:
        self.connection.send_multipart(message.to_frames())

    def read_raw(self, timeout: Optional[float] = None) -> list[bytes]:
        # deprecated
        warn("`read_raw` is deprecated, use `_read_socket_message` instead.", FutureWarning)
        if self.poll(timeout=int(timeout or self.timeout * 1000)):
            return self.connection.recv_multipart()
        else:
            self._reading = self.connection.recv_multipart
            raise TimeoutError("Reading timed out.")

    def poll(self, timeout: Optional[float] = None) -> int:
        """Check how many messages arrived."""
        if timeout is None:
            timeout = self.timeout
        return self.connection.poll(timeout=timeout * 1000)  # in ms

    def _read_socket_message(self, timeout: Optional[float] = None) -> Message:
        """Read the next message from the socket, without further processing."""
        if self.connection.poll(int(timeout or self.timeout * 1000)):
            return Message.from_frames(*self.connection.recv_multipart())
        raise TimeoutError("Reading timed out")

    def handle_not_signed_in(self):
        super().handle_not_signed_in()
        raise ConnectionResetError("Have not been signed in, signing in.")

    def ask_raw(self, message: Message, timeout: Optional[float] = None) -> Message:
        """Send and read the answer, signing in if necessary."""
        for _ in range(2):
            try:
                return super().ask_message(message=message, timeout=timeout)
            except ConnectionResetError:
                pass  # sign in required, retry
        raise

    def ask_message(self, message: Message, timeout: Optional[float] = None) -> Message:
        """Send a message and retrieve the response."""
        response = self.ask_raw(message=message, timeout=timeout)
        if response.sender_elements.name == b"COORDINATOR":
            try:
                error = response.data.get("error")  # type: ignore
            except AttributeError:
                pass
            else:
                if error:
                    # TODO define how to transmit that information
                    raise ConnectionError(str(error))
        return response

    def ask_json(self, receiver: Union[bytes, str], json_string: str,
                 timeout: Optional[float] = None
                 ) -> bytes:
        message = Message(receiver=receiver, data=json_string, message_type=MessageTypes.JSON)
        response = self.ask_message(message=message, timeout=timeout)
        return response.payload[0]

    # Messages
    def sign_in(self) -> None:
        """Sign in to the Coordinator and return the node."""
        self.namespace = None
        self._last_beat = perf_counter()  # to not sign in again...
        super().sign_in()

    def get_capabalities(self, receiver: Union[bytes, str]) -> dict:
        return self.ask_rpc(receiver=receiver, method="rpc.discover")
