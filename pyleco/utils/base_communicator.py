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
from time import perf_counter
from typing import Optional, Protocol

import zmq

from ..core.internal_protocols import CommunicatorProtocol
from ..core.message import Message, MessageTypes
from ..json_utils.errors import JSONRPCError, DUPLICATE_NAME, NOT_SIGNED_IN


NOT_SIGNED_IN_ERROR_CODE = str(NOT_SIGNED_IN.code).encode()


class MessageBuffer:
    _messages: list[Message]
    _requested_ids: set[bytes]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._messages = []
        self._requested_ids = set()

    def add_conversation_id(self, conversation_id: bytes) -> None:
        """Add a conversation_id such that its response has to be recalled by name."""
        self._requested_ids.add(conversation_id)

    def remove_conversation_id(self, conversation_id: bytes) -> None:
        """Remove a conversation_id from the requested ids."""
        self._requested_ids.discard(conversation_id)

    def is_conversation_id_requested(self, conversation_id: bytes) -> bool:
        """Check whether this conversation_id is requested by someone."""
        return conversation_id in self._requested_ids

    def add_message(self, message: Message):
        """Add a message to the buffer."""
        self._messages.append(message)

    def retrieve_message(self, conversation_id: Optional[bytes] = None) -> Optional[Message]:
        """Retrieve the requested message or the next free one for `conversation_id=None`."""
        for i, msg in enumerate(self._messages):
            cid = msg.conversation_id
            if conversation_id == cid:
                self._requested_ids.discard(cid)
                return self._messages.pop(i)
            elif cid not in self._requested_ids and conversation_id is None:
                return self._messages.pop(i)
        return None

    def __len__(self):
        return len(self._messages)


class BaseCommunicator(CommunicatorProtocol, Protocol):
    """Abstract class of a Communicator with some logic.
    """

    socket: zmq.Socket
    log: logging.Logger
    namespace: Optional[str]
    message_buffer: MessageBuffer

    # Setup methods for call in init
    def setup_message_buffer(self) -> None:
        """Create the message buffer variables."""
        self.message_buffer = MessageBuffer()

    def close(self) -> None:
        """Close the connection."""
        self.socket.close(1)

    # Context manager
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    # Base communication
    def _send_socket_message(self, message: Message) -> None:
        self.socket.send_multipart(message.to_frames())

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
            self.interpret_rpc_response(msg)
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
    def _read_socket_message(self, timeout: Optional[float] = None) -> Message:
        """Read the next message from the socket, without further processing."""
        if self.socket.poll(int((timeout if timeout is not None else self.timeout) * 1000)):
            return Message.from_frames(*self.socket.recv_multipart())
        raise TimeoutError("Reading timed out")

    def _find_socket_message(self, conversation_id: Optional[bytes] = None,
                             timeout: Optional[float] = None,
                             ) -> Message:
        """Find a specific message among socket messages, storing the other ones in the buffer.

        :param conversation_id: Conversation ID to filter for, or next free message if None.
        """
        stop = perf_counter() + (timeout if timeout is not None else self.timeout)
        while True:
            msg = self._read_socket_message(timeout)
            self.check_for_not_signed_in_error(message=msg)
            cid = msg.conversation_id
            if conversation_id == cid:
                self.message_buffer.remove_conversation_id(conversation_id=cid)
                return msg
            elif self.message_buffer.is_conversation_id_requested(conversation_id=cid):
                self.message_buffer.add_message(msg)
            elif conversation_id is None:
                return msg
            else:
                self.message_buffer.add_message(msg)
            if perf_counter() > stop:
                # inside the loop to do it at least once, even if timeout is 0
                break
        raise TimeoutError("Message not found.")

    def check_for_not_signed_in_error(self, message: Message) -> None:
        if (message.sender_elements.name == b"COORDINATOR"
                and message.payload
                and b"error" in message.payload[0]
                and NOT_SIGNED_IN_ERROR_CODE in message.payload[0]):
            self.handle_not_signed_in()

    def read_message(self, conversation_id: Optional[bytes] = None,
                     timeout: Optional[float] = None) -> Message:
        message = self.message_buffer.retrieve_message(conversation_id=conversation_id)
        if message is None:
            message = self._find_socket_message(conversation_id=conversation_id, timeout=timeout)
        return message

    def handle_not_signed_in(self) -> None:
        self.namespace = None
        self.sign_in()
        self.log.warning("I was not signed in, signing in.")

    def ask_message(self, message: Message, timeout: Optional[float] = None) -> Message:
        self.send_message(message=message)
        return self.read_message(conversation_id=message.conversation_id, timeout=timeout)
