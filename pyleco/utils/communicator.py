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
from time import perf_counter
from typing import Any, Callable, Optional

from jsonrpcobjects.errors import JSONRPCError
import zmq

from ..core import COORDINATOR_PORT
from ..core.internal_protocols import CommunicatorProtocol
from ..core.message import Message
from ..core.rpc_generator import RPCGenerator, INVALID_SERVER_RESPONSE
from ..errors import DUPLICATE_NAME, NOT_SIGNED_IN


class Communicator(CommunicatorProtocol):
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
    :param int timeout: Timeout in ms.
    :param bool auto_open: Open automatically a connection upon instantiation.
    :param str protocol: Protocol name to use.
    :param bool standalone: Whether to bind to the port in standalone mode.
    """

    def __init__(
        self,
        name: str,
        host: str = "localhost",
        port: Optional[int] = COORDINATOR_PORT,
        timeout: int = 100,
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
        self._last_beat: float = 0
        self._reading: Optional[Callable[[], list[bytes]]] = None
        self.rpc_generator = RPCGenerator()
        super().__init__(**kwargs)

    def open(self) -> None:
        """Open the connection."""
        context = zmq.Context.instance()
        self.connection = context.socket(zmq.DEALER)
        protocol, standalone = self._conn_details
        if standalone:
            self.connection.bind(f"{protocol}://*:{self.port}")
        else:
            self.connection.connect(f"{protocol}://{self.host}:{self.port}")

    def close(self) -> None:
        """Close the connection."""
        try:
            if not self.connection.closed:
                self.sign_out()
                self.connection.close(1)
        except (AttributeError, TimeoutError):
            pass

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

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        """Called after the with clause has finished, does cleanup."""
        self.close()

    def retry_read(self, timeout: Optional[int] = None) -> list[bytes] | None:
        """Retry reading."""
        if self._reading and self.connection.poll(timeout or self.timeout):
            return self._reading()
        else:
            return None

    def send_message(self, message: Message) -> None:
        now = perf_counter()
        if now > self._last_beat + 15:
            self.sign_in()
        self._last_beat = now
        if not message.sender:
            message.sender = (".".join(
                (self.namespace, self.name)) if self.namespace else self.name).encode()
        frames = message.to_frames()
        self.connection.send_multipart(frames)

    def read_raw(self, timeout: Optional[int] = None) -> list[bytes]:
        if self.connection.poll(timeout or self.timeout):
            return self.connection.recv_multipart()
        else:
            self._reading = self.connection.recv_multipart
            raise TimeoutError("Reading timed out.")

    def poll(self) -> int:
        """Check how many messages arrived."""
        return self.connection.poll()

    def read(self) -> Message:
        return Message.from_frames(*self.read_raw())

    def ask_raw(self, message: Message) -> Message:
        """Send and read the answer, signing in if necessary."""
        self.send_message(message=message)
        cid = message.conversation_id
        while True:
            response = self.read()
            # skip pings as we either are still signed in or going to sign in again.
            if b"jsonrpc" in response.payload[0] and isinstance(response.data, dict):
                if response.data.get("method") == "pong":
                    continue
                elif (error := response.data.get("error")):
                    code = error.get("code")
                    if code == NOT_SIGNED_IN.code:
                        self.log.error("I'm not signed in, signing in.")
                        self.sign_in()
                        self.send_message(message=message)
                        continue
                    elif code == DUPLICATE_NAME.code:
                        self.log.error(f"Sign in failed: {DUPLICATE_NAME.message}")
                        raise ConnectionRefusedError(f"Sign in failed: {DUPLICATE_NAME.message}")
            if cid == response.conversation_id:
                return response
            else:
                self.log.warning(f"Message with different conversation id received: {response}.")

    def ask_message(self, message: Message) -> Message:
        """Send a message and retrieve the response."""
        response = self.ask_raw(message=message)
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

    def ask_rpc(self, receiver: bytes | str, method: str, **kwargs) -> Any:
        """Send a rpc call and return the result or raise an error."""
        send_json = self.rpc_generator.build_request_str(method=method, **kwargs)
        response_json = self.ask_json(receiver=receiver, json_string=send_json)
        try:
            result = self.rpc_generator.get_result_from_response(response_json)
        except JSONRPCError as exc:
            if exc.rpc_error.code == INVALID_SERVER_RESPONSE.code:
                self.log.exception(f"Decoding failed for {response_json!r}.", exc_info=exc)
                return
            else:
                self.log.exception(f"Some error happened {response_json!r}.", exc_info=exc)
                raise
        return result

    def ask_json(self, receiver: bytes | str, json_string: str) -> bytes:
        message = Message(receiver=receiver, data=json_string)
        response = self.ask_message(message=message)
        return response.payload[0]

    # Messages
    def sign_in(self) -> None:
        """Sign in to the Coordinator and return the node."""
        self.namespace = None
        self._last_beat = perf_counter()  # to not sign in again...
        json_string = self.rpc_generator.build_request_str(method="sign_in")
        request = Message(receiver=b"COORDINATOR", data=json_string)
        cid0 = request.conversation_id
        response = self.ask_raw(message=request)
        if b"error" in response.payload[0]:
            raise ConnectionError
        assert (
            response.conversation_id == cid0
        ), (f"Answer to another request (mine {cid0!r}) received from {response.sender!r}: "
            f"{response.conversation_id!r}, '{response.data}'.")
        self.namespace = response.sender_elements.namespace.decode()
        self.log.info(f"Signed in to '{self.namespace}'.")

    def sign_out(self) -> None:
        """Tell the Coordinator to drop references."""
        try:
            self.ask_rpc(b"COORDINATOR", method="sign_out")
        except JSONRPCError:
            self.log.error("JSON decoding at sign out failed.")

    def get_capabalities(self, receiver: bytes | str) -> dict:
        return self.ask_rpc(receiver=receiver, method="rpc.discover")

    def heartbeat(self) -> None:
        """Send a heartbeat to the connected Coordinator."""
        self.send_message(message=Message(receiver=b"COORDINATOR"))
