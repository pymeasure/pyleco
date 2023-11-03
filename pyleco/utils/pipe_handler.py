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

from threading import get_ident, Condition
from typing import Callable, Optional
from warnings import warn

import zmq

from ..core import PROXY_SENDING_PORT
from .extended_message_handler import ExtendedMessageHandler
from ..core.message import Message
from ..core.internal_protocols import CommunicatorProtocol


class MessageBuffer:
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
    _result: Message

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Storage for returning asked messages
        self._buffer: list[Message] = []
        self._buffer_lock = Condition()
        self._cids: list[bytes] = []  # List of conversation_ids of asked questions.

    def add_conversation_id(self, conversation_id: bytes) -> None:
        """Add the conversation_id of a sent message."""
        with self._buffer_lock:
            self._cids.append(conversation_id)

    def add_response_message(self, message: Message) -> bool:
        """Add a message to the buffer, if it is a requested response.

        :return: whether was added to the buffer.
        """
        with self._buffer_lock:
            if message.conversation_id in self._cids:
                self._buffer.append(message)
                del self._cids[self._cids.index(message.conversation_id)]
                self._buffer_lock.notify_all()
                return True
            else:
                return False

    def _predicate_generator(self, conversation_id: bytes) -> Callable[[], bool]:
        def check_message_in_buffer() -> bool:
            for (i, message) in enumerate(self._buffer):
                if message.conversation_id == conversation_id:
                    del self._buffer[i]
                    self._result = message
                    return True
            return False
        return check_message_in_buffer

    def retrieve_message(self, conversation_id: bytes, tries: Optional[int] = None,
                         timeout: float = 1) -> Message:
        """Retrieve a message with a certain `conversation_id`.

        Try to read up to `tries` messages, waiting each time up to `timeout`.

        :param conversation_id: Conversation_id of the message to retrieve.
        :param tries: *Deprecated* How many messages or timeouts should be read.
        :param timeout: Timeout in seconds for a single trial.
        """
        if tries is not None:
            warn("`tries` is deprecated as it is not used anymore.", FutureWarning)
        with self._buffer_lock:
            found = self._buffer_lock.wait_for(
                self._predicate_generator(conversation_id=conversation_id),
                timeout=timeout)
            if found:
                return self._result
        # No result found:
        raise TimeoutError("Reading timed out.")

    def __len__(self):
        return len(self._buffer)


class CommunicatorPipe(CommunicatorProtocol):
    """A pipe endpoint satisfying the communicator protocol.

    You can create this endpoint in any thread you like and use it there.
    """

    def __init__(self,
                 parent: ExtendedMessageHandler,
                 pipe_port: int,
                 buffer: MessageBuffer,
                 context: Optional[zmq.Context] = None,
                 **kwargs):
        super().__init__(**kwargs)
        self.parent = parent
        context = context or zmq.Context.instance()
        self.socket: zmq.Socket = context.socket(zmq.PAIR)
        self.socket.connect(f"inproc://listenerPipe:{pipe_port}")
        self.rpc_generator = parent.rpc_generator
        self.buffer = buffer

    @property
    def name(self) -> str:
        return self.parent.name

    @name.setter
    def name(self, value: str | bytes) -> None:
        if isinstance(value, str):
            value = value.encode()
        self._send_pipe_message(b"REN", value)

    @property
    def namespace(self) -> str | None:
        return self.parent.namespace

    @property
    def full_name(self) -> str:
        return self.parent.full_name

    def _send_pipe_message(self, typ: bytes, *content: bytes) -> None:
        self.socket.send_multipart((typ, *content))

    def send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.full_name.encode()
        self._send_pipe_message(b"SND", *message.to_frames())

    def subscribe(self, topic: bytes | str) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        self._send_pipe_message(b"SUB", topic)

    def unsubscribe(self, topic: bytes | str) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        self._send_pipe_message(b"UNSUB", topic)

    def unsubscribe_all(self) -> None:
        self._send_pipe_message(b"UNSUBALL")

    def read_message(self, conversation_id: bytes, **kwargs) -> Message:
        return self.buffer.retrieve_message(conversation_id=conversation_id, **kwargs)

    def ask_message(self, message: Message, timeout: float = 1) -> Message:
        self.buffer.add_conversation_id(message.conversation_id)
        self.send_message(message=message)
        return self.read_message(conversation_id=message.conversation_id, timeout=timeout)

    def sign_in(self) -> None:
        return  # to satisfy the protocol

    def sign_out(self) -> None:
        return  # to satisfy the protocol

    def close(self) -> None:
        self.socket.close(1)


class PipeHandler(ExtendedMessageHandler):
    """A message handler which offers thread-safe methods for sending/reading messages.

    This message handler offers the thread-safe :meth:`get_communicator` method to create a
    communicator in a thread different to the handlers thread.
    These communicator instances (in different threads) can communicate with the single message
    handler savely.
    The normal usage is to have the Pipehandler in some background thread listening ):meth:`listen`)
    while the "active" threads have each a Communicator.
    """
    _communicators: dict[int, CommunicatorPipe]

    def __init__(self, name: str, context: Optional[zmq.Context] = None, **kwargs) -> None:
        context = context or zmq.Context.instance()
        super().__init__(name=name, context=context, **kwargs)
        self.internal_pipe: zmq.Socket = context.socket(zmq.PULL)
        self.pipe_port = self.internal_pipe.bind_to_random_port("inproc://listenerPipe",
                                                                min_port=12345)
        self.buffer = MessageBuffer()
        self._communicators = {}
        self.name_changing_methods: list[Callable[[str], None]] = []

    def close(self) -> None:
        self.internal_pipe.close(1)
        super().close()

    def set_full_name(self, full_name: str) -> None:
        super().set_full_name(full_name=full_name)
        for method in self.name_changing_methods:
            try:
                method(full_name)
            except Exception as exc:
                self.log.exception("Setting the name with a registered method failed.",
                                   exc_info=exc)

    def _listen_setup(self, host: str = "localhost", data_port: int = PROXY_SENDING_PORT,
                      **kwargs) -> zmq.Poller:
        poller = super()._listen_setup(host=host, data_port=data_port, **kwargs)
        poller.register(self.internal_pipe, zmq.POLLIN)
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: int | None
                             ) -> dict[zmq.Socket, int]:
        socks = super()._listen_loop_element(poller=poller, waiting_time=waiting_time)
        if self.internal_pipe in socks:
            self.handle_pipe_message()
            del socks[self.internal_pipe]
        return socks

    def handle_pipe_message(self) -> None:
        msg = self.internal_pipe.recv_multipart()
        # HACK noqa due to spyder "match"
        match msg:  # noqa
            case [b"SUB", topic]:  # noqa: 211
                self.subscribe_single(topic=topic)
            case [b"UNSUB", topic]:  # noqa: 211
                self.unsubscribe_single(topic=topic)
            case [b"UNSUBALL"]:  # noqa: 211
                self.unsubscribe_all()
            case [b"SND", *message]:  # noqa: 211
                self._send_frames(frames=message)
            case [b"REN", new_name]:  # noqa: 211
                self.sign_out()
                self.name = new_name.decode()
                self.sign_in()
            case msg:
                self.log.debug(f"Received unknown '{msg}'.")

    # Control protocol
    def _send_frames(self, frames: list[bytes]):
        """Send frames over the connection."""
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def handle_commands(self, message: Message) -> None:
        """Handle commands: collect a requested response or give to :meth:`finish_handle_message`.
        """
        if not self.buffer.add_response_message(message):
            self.finish_handle_commands(message)

    def finish_handle_commands(self, message: Message) -> None:
        """Handle commands not requested via ask."""
        super().handle_commands(message)

    # Thread safe methods for access from other threads
    def create_communicator(self, context: Optional[zmq.Context] = None) -> CommunicatorPipe:
        """Create a communicator wherever you want to access the pipe handler."""
        com = CommunicatorPipe(buffer=self.buffer, pipe_port=self.pipe_port,
                               parent=self, context=context)
        self._communicators[get_ident()] = com
        return com

    def get_communicator(self, context: Optional[zmq.Context] = None) -> CommunicatorPipe:
        """Get the communicator for this thread, creating one if necessary."""
        com = self._communicators.get(get_ident())
        if com is None or com.socket.closed is True:
            return self.create_communicator(context=context)
        else:
            return com

    # TODO the methods below are deprecated, use the CommunicatorPipe instead
    def pipe_setup(self, context: Optional[zmq.Context] = None) -> None:
        """Create the pipe in the external thread."""
        self.external_pipe = self.get_communicator(context=context)

    def pipe_close(self) -> None:
        """Close the pipe."""
        self.external_pipe.close()

    def pipe_send_message(self, message: Message):
        self.external_pipe.send_message(message=message)

    def pipe_read_message(self, conversation_id: bytes, timeout: float = 1) -> Message:
        return self.buffer.retrieve_message(conversation_id=conversation_id, timeout=timeout)

    def pipe_ask(self, message: Message, timeout: float = 1, tries: int = 1) -> Message:
        return self.external_pipe.ask_message(message=message)

    def pipe_subscribe(self, topic: str | bytes) -> None:
        self.external_pipe.subscribe(topic)

    def pipe_unsubscribe(self, topic: str | bytes) -> None:
        self.external_pipe.unsubscribe(topic)

    def pipe_unsubscribe_all(self) -> None:
        self.external_pipe.unsubscribe_all()

    def pipe_rename_component(self, new_name: str | bytes) -> None:
        self.external_pipe.name = new_name
