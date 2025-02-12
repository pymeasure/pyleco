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
from enum import Enum
from threading import get_ident, Condition
from typing import Any, Callable, Optional, Union
from warnings import warn

import zmq

from .extended_message_handler import ExtendedMessageHandler
from .base_communicator import MessageBuffer
from ..core.message import Message, MessageTypes
from ..core.internal_protocols import CommunicatorProtocol, SubscriberProtocol
from ..core.serialization import generate_conversation_id


class PipeCommands(bytes, Enum):
    SUBSCRIBE = b"SUB"
    UNSUBSCRIBE = b"UNSUB"
    UNSUBSCRIBE_ALL = b"UNSUBALL"
    SEND = b"SND"
    RENAME = b"REN"
    LOCAL_COMMAND = b"LOC"


class LockedMessageBuffer(MessageBuffer):
    """Buffer messages thread safe for later reading by the application.

    With the method :meth:`add_conversation_id` a conversation_id is stored to indicate, that the
    corresponding response should be stored in the buffer instead of handling it in the
    message_handler.
    The message_handler uses :meth:`add_response_message` to add a message to the buffer, if it is a
    response, i.e. its conversation_id is in the list of expected responses.
    The main application thread uses :meth:`retrieve_message` to get the response message with a
    specific conversation_id.
    If the response is in the buffer, it is returned immediately.
    If the response is not yet in the buffer, it waits until a new message is added to the buffer to
    check, whether that message fits the conversation_id.
    This is repeated until the suiting response is found or a limit is reached.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._buffer_lock = Condition()

    def add_conversation_id(self, conversation_id: bytes) -> None:
        """Add the conversation_id of a sent message in order to buffer the response."""
        with self._buffer_lock:
            super().add_conversation_id(conversation_id=conversation_id)

    def remove_conversation_id(self, conversation_id: bytes) -> None:
        """Remove a conversation_id from the requested ids."""
        with self._buffer_lock:
            super().remove_conversation_id(conversation_id=conversation_id)

    def add_message(self, message: Message):
        """Add a message to the buffer."""
        with self._buffer_lock:
            super().add_message(message)
            self._buffer_lock.notify_all()

    def add_response_message(self, message: Message) -> bool:
        """Add a message to the buffer, if it is a requested response.

        .. deprecated:: 0.3
            Use :meth:`add_message` instead.

        :return: whether the message was added to the buffer.
        """
        warn("`add_response_message` is deprecated, use `add_message` instead.", FutureWarning)
        if self.is_conversation_id_requested(message.conversation_id):
            self.add_message(message)
            return True
        else:
            return False

    def retrieve_message(self, conversation_id: Optional[bytes] = None) -> Optional[Message]:
        """Retrieve the requested message or the next free one for `conversation_id=None`."""
        with self._buffer_lock:
            return super().retrieve_message(conversation_id=conversation_id)

    def _retrieve_message_without_lock(self, conversation_id: Optional[bytes]) -> Optional[Message]:
        return super().retrieve_message(conversation_id=conversation_id)

    def _predicate_generator(self, conversation_id: bytes) -> Callable[[], Optional[Message]]:
        def check_message_in_buffer() -> Optional[Message]:
            return self._retrieve_message_without_lock(
                conversation_id=conversation_id)
        return check_message_in_buffer

    def wait_for_message(self, conversation_id: bytes, timeout: float = 1) -> Message:
        """Retrieve a message with a certain `conversation_id` waiting `timeout` seconds.

        :param conversation_id: Conversation_id of the message to retrieve.
        :param timeout: Timeout in seconds.
        """
        with self._buffer_lock:
            result = self._buffer_lock.wait_for(
                self._predicate_generator(conversation_id=conversation_id),
                timeout=timeout)
            if result:
                return result
        # No result found:
        raise TimeoutError("Reading timed out.")


class CommunicatorPipe(CommunicatorProtocol, SubscriberProtocol):
    """A pipe endpoint satisfying the communicator protocol.

    You can create this endpoint in any thread you like and use it there.
    """

    def __init__(self,
                 handler: ExtendedMessageHandler,
                 pipe_port: int,
                 message_buffer: LockedMessageBuffer,
                 context: Optional[zmq.Context] = None,
                 timeout: float = 1,
                 **kwargs):
        super().__init__(**kwargs)
        self.handler = handler
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.PAIR)
        self.socket.connect(f"inproc://listenerPipe:{pipe_port}")
        self.rpc_generator = handler.rpc_generator
        self.message_buffer = message_buffer
        self.buffer = self.message_buffer  # for backward compatibility
        self.timeout = timeout

    # CommunicatorProtocol
    @property
    def name(self) -> str:
        return self.handler.name

    @name.setter
    def name(self, value: Union[bytes, str]) -> None:
        if isinstance(value, str):
            value = value.encode()
        self._send_pipe_message(PipeCommands.RENAME, value)

    @property
    def namespace(self) -> Union[str, None]:  # type: ignore[override]
        return self.handler.namespace

    @property
    def full_name(self) -> str:
        return self.handler.full_name

    def _send_pipe_message(self, typ: PipeCommands, *content: bytes) -> None:
        try:
            self.socket.send_multipart((typ, *content))
        except zmq.ZMQError as exc:
            raise ConnectionRefusedError(f"Connection to the handler refused with '{exc}', "
                                         "probably the handler stopped.")

    def send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.full_name.encode()
        self._send_pipe_message(PipeCommands.SEND, *message.to_frames())

    def read_message(self, conversation_id: Optional[bytes], timeout: Optional[float] = None
                     ) -> Message:
        if conversation_id is None:
            raise ValueError("You have to request a message with its conversation_id.")
        return self.message_buffer.wait_for_message(
            conversation_id=conversation_id,
            timeout=self.timeout if timeout is None else timeout,
        )

    def ask_message(self, message: Message, timeout: Optional[float] = None) -> Message:
        self.message_buffer.add_conversation_id(message.conversation_id)
        self.send_message(message=message)
        return self.read_message(conversation_id=message.conversation_id, timeout=timeout)

    def sign_in(self) -> None:
        raise NotImplementedError("Managed in the PipeHandler itself.")

    def sign_out(self) -> None:
        raise NotImplementedError("Managed in the PipeHandler itself.")

    def close(self) -> None:
        self.socket.close(1)

    # methods for the data protocol
    def subscribe_single(self, topic: bytes) -> None:
        self._send_pipe_message(PipeCommands.SUBSCRIBE, topic)

    def unsubscribe_single(self, topic: bytes) -> None:
        self._send_pipe_message(PipeCommands.UNSUBSCRIBE, topic)

    def unsubscribe_all(self) -> None:
        self._send_pipe_message(PipeCommands.UNSUBSCRIBE_ALL)

    # methods for local access
    def _send_handler(self, method: str, **kwargs) -> bytes:
        cid = generate_conversation_id()
        message_string = self.rpc_generator.build_request_str(method=method, **kwargs)
        self.message_buffer.add_conversation_id(cid)
        self._send_pipe_message(PipeCommands.LOCAL_COMMAND, cid, message_string.encode())
        return cid

    def _read_handler(self, cid: bytes, timeout: float = 1) -> Any:
        response_message = self.read_message(conversation_id=cid, timeout=timeout)
        return self.interpret_rpc_response(response_message=response_message)

    def ask_handler(self, method: str, timeout: float = 1, **kwargs) -> Any:
        """Ask the associated message handler."""
        cid = self._send_handler(method=method, **kwargs)
        return self._read_handler(cid, timeout=timeout)

    # Utility methods
    def register_rpc_method(self, method: Callable, **kwargs) -> None:
        """Register a method with the message handler to make it available via RPC."""
        self.handler.register_rpc_method(method=method, **kwargs)


class PipeHandler(ExtendedMessageHandler):
    """A message handler which offers thread-safe methods for sending/reading messages.

    This message handler offers the thread-safe :meth:`get_communicator` method to create a
    communicator in a thread different to the handlers thread.
    These communicator instances (in different threads) can communicate with the single message
    handler safely.
    The normal usage is to have the Pipehandler in some background thread listening ):meth:`listen`)
    while the "active" threads have each a Communicator.

    :attr name_changing_methods: List of methods which are called, whenever the full_name changes.
    """
    message_buffer: LockedMessageBuffer
    _communicators: dict[int, CommunicatorPipe]
    _on_name_change_methods: set[Callable[[str], None]] = set()

    def __init__(self, name: str, context: Optional[zmq.Context] = None, **kwargs) -> None:
        context = context or zmq.Context.instance()
        super().__init__(name=name, context=context, **kwargs)
        self.internal_pipe: zmq.Socket = context.socket(zmq.PULL)
        self.pipe_port = self.internal_pipe.bind_to_random_port("inproc://listenerPipe",
                                                                min_port=12345)
        self._communicators = {}

    def setup_message_buffer(self) -> None:
        self.message_buffer = LockedMessageBuffer()

    def close(self) -> None:
        self.internal_pipe.close(1)
        self.close_all_communicators()
        super().close()

    def set_full_name(self, full_name: str) -> None:
        super().set_full_name(full_name=full_name)
        for method in self._on_name_change_methods:
            try:
                method(full_name)
            except Exception as exc:
                self.log.exception("Setting the name with a registered method failed.",
                                   exc_info=exc)

    def register_on_name_change_method(self, method: Callable[[str], None]) -> None:
        """Register a method (accepting a string) to be called whenever the full name changes."""
        self._on_name_change_methods.add(method)

    def unregister_on_name_change_method(self, method: Callable[[str], None]) -> None:
        self._on_name_change_methods.discard(method)

    def _listen_setup(self, **kwargs) -> zmq.Poller:
        poller = super()._listen_setup(**kwargs)
        poller.register(self.internal_pipe, zmq.POLLIN)
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: Optional[int]
                             ) -> dict[zmq.Socket, int]:
        socks = super()._listen_loop_element(poller=poller, waiting_time=waiting_time)
        if self.internal_pipe in socks:
            self.read_and_handle_pipe_message()
            del socks[self.internal_pipe]
        return socks

    def read_and_handle_pipe_message(self) -> None:
        msg = self.internal_pipe.recv_multipart()
        self.handle_pipe_message(msg)

    def handle_pipe_message(self, msg: list[bytes]) -> None:
        cmd = msg[0]
        if cmd == PipeCommands.SUBSCRIBE:
            self.subscribe_single(topic=msg[1])
        elif cmd == PipeCommands.UNSUBSCRIBE:
            self.unsubscribe_single(topic=msg[1])
        elif cmd == PipeCommands.UNSUBSCRIBE_ALL:
            self.unsubscribe_all()
        elif cmd == PipeCommands.SEND:
            self._send_frames(frames=msg[1:])
        elif cmd == PipeCommands.RENAME:
            self.rename_handler(msg[1].decode())
        elif cmd == PipeCommands.LOCAL_COMMAND:
            self.handle_local_request(conversation_id=msg[1], rpc=msg[2])
        else:
            self.log.debug(f"Received unknown '{msg}'.")

    def rename_handler(self, name):
        self.sign_out()
        self.name = name
        self.namespace = None  # to update the full_name
        self.sign_in()

    # Control protocol
    def _send_frames(self, frames: list[bytes]) -> None:
        """Send frames over the connection."""
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    # Local messages
    def handle_local_request(self, conversation_id: bytes, rpc: bytes) -> None:
        result = self.rpc.process_request(data=rpc)
        self.message_buffer.add_message(
            Message(
                "comm",
                sender="ego",
                data=result,
                message_type=MessageTypes.JSON,
                conversation_id=conversation_id,
            )
        )

    # Thread safe methods for access from other threads
    def create_communicator(self, **kwargs) -> CommunicatorPipe:
        """Create a communicator wherever you want to access the pipe handler."""
        com = CommunicatorPipe(message_buffer=self.message_buffer, pipe_port=self.pipe_port,
                               handler=self,
                               **kwargs)
        self._communicators[get_ident()] = com
        return com

    def get_communicator(self, **kwargs) -> CommunicatorPipe:
        """Get the communicator for this thread, creating one if necessary."""
        com = self._communicators.get(get_ident())
        if com is None or com.socket.closed is True:
            return self.create_communicator(**kwargs)
        else:
            return com

    def close_all_communicators(self) -> None:
        for communicator in self._communicators.values():
            communicator.close()
