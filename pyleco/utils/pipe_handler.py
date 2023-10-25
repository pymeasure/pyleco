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

from threading import Lock, Event
from typing import Optional

import zmq

from ..core import PROXY_SENDING_PORT
from .extended_message_handler import ExtendedMessageHandler
from ..core.message import Message


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

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        # Storage for returning asked messages
        self._buffer: list[Message] = []
        self._buffer_lock = Lock()
        self._event = Event()
        self._cids: list[bytes] = []  # List of conversation_ids of asked questions.

    def add_conversation_id(self, conversation_id: bytes) -> None:
        """Add the conversation_id of a sent message."""
        self._event.clear()
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
                self._event.set()
                return True
            else:
                return False

    def _check_message_in_buffer(self, conversation_id: bytes) -> Message | None:
        """Check the buffer for a message with the specified id."""
        with self._buffer_lock:
            for (i, message) in enumerate(self._buffer):
                if message.conversation_id == conversation_id:
                    del self._buffer[i]
                    return message
        return None

    def retrieve_message(self, conversation_id: bytes, tries: int = 10,
                         timeout: float = 0.1) -> Message:
        """Retrieve a message with a certain `conversation_id`.

        Try to read up to `tries` messages, waiting each time up to `timeout`.

        :param conversation_id: Conversation_id of the message to retrieve.
        :param tries: How many messages or timeouts should be read.
        :param timeout: Timeout in seconds for a single trial.
        """
        if (result := self._check_message_in_buffer(conversation_id=conversation_id)) is not None:
            return result
        for _ in range(tries):
            if self._event.wait(timeout):
                self._event.clear()
                if (result := self._check_message_in_buffer(conversation_id)) is not None:
                    return result
        # No result found:
        raise TimeoutError("Reading timed out.")


class PipeHandler(ExtendedMessageHandler):
    """A message handler which offers thread-safe methods for sending/reading messages.

    Methods prefixed with `pipe_` are thread-safe.
    """

    def __init__(self, name: str, context: Optional[zmq.Context] = None, **kwargs) -> None:
        context = context or zmq.Context.instance()
        super().__init__(name=name, context=context, **kwargs)
        self.internal_pipe: zmq.Socket = context.socket(zmq.PAIR)
        self.pipe_port = self.internal_pipe.bind_to_random_port("inproc://listenerPipe",
                                                                min_port=12345)
        self.buffer = MessageBuffer()

    class Pipe:
        """Pipe endpoint with lock."""

        def __init__(self, socket: zmq.Socket, **kwargs) -> None:
            super().__init__(**kwargs)
            self.socket = socket
            self.lock = Lock()

        def send_multipart(self, frames: list[bytes] | tuple[bytes, ...]) -> None:
            """Send a multipart message with frames (list type) ensuring lock."""
            self.lock.acquire()
            self.socket.send_multipart(frames)
            self.lock.release()

        def close(self, linger: int | None = 0) -> None:
            self.socket.close(linger=linger)

    def close(self) -> None:
        self.internal_pipe.close(1)
        super().close()

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
        # HACK noq due to spyder "match"
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
        try:
            json = b"id" in message.payload[0] and (b"result" in message.payload[0]
                                                    or b"error" in message.payload[0])
        except (IndexError, KeyError):
            json = False
        if json and self.buffer.add_response_message(message):
            pass
        else:
            self.finish_handle_commands(message)

    def finish_handle_commands(self, message: Message) -> None:
        """Handle commands not requested via ask."""
        super().handle_commands(message)

    # Thread safe methods for access from other threads
    def pipe_setup(self, context: Optional[zmq.Context] = None) -> None:
        """Create the pipe in the external thread."""
        context = context or zmq.Context.instance()
        external_pipe_socket: zmq.Socket = context.socket(zmq.PAIR)
        external_pipe_socket.connect(f"inproc://listenerPipe:{self.pipe_port}")
        self.external_pipe = self.Pipe(socket=external_pipe_socket)

    def pipe_close(self) -> None:
        """Close the pipe."""
        self.external_pipe.close(1)

    def pipe_send_message(self, message: Message):
        if not message.sender:
            message.sender = self.full_name.encode()
        self.external_pipe.send_multipart((b"SND", *message.to_frames()))

    def pipe_read_message(self, conversation_id: bytes, tries: int = 10,
                          timeout: float = 0.1) -> Message:
        return self.buffer.retrieve_message(conversation_id=conversation_id, tries=tries,
                                            timeout=timeout)

    def pipe_ask(self, message: Message, tries: int = 10, timeout: float = 0.1) -> Message:
        self.buffer.add_conversation_id(message.conversation_id)
        self.pipe_send_message(message=message)
        return self.pipe_read_message(conversation_id=message.conversation_id, tries=tries,
                                      timeout=timeout)

    def pipe_subscribe(self, topic: str | bytes) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        self.external_pipe.send_multipart((b"SUB", topic))

    def pipe_unsubscribe(self, topic: str | bytes) -> None:
        if isinstance(topic, str):
            topic = topic.encode()
        self.external_pipe.send_multipart((b"UNSUB", topic))

    def pipe_unsubscribe_all(self) -> None:
        self.external_pipe.send_multipart((b"UNSUBALL",))

    def pipe_rename_component(self, new_name: str | bytes) -> None:
        if isinstance(new_name, str):
            new_name = new_name.encode()
        self.external_pipe.send_multipart((b"REN", new_name))
