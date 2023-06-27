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

import json
import pickle
from threading import Thread, Lock, Event
from typing import List, Tuple, Optional

import zmq

from .message_handler import MessageHandler
from .publisher import Publisher
from ..core.message import Message
from ..core.serialization import create_header_frame, generate_conversation_id, compose_message
from ..core.rpc_generator import RPCGenerator
from .timers import RepeatingTimer


class BaseListener(MessageHandler):
    """Listening on published data and opening a configuration port, both in a separate thread.

    It works on one side like a :class:`Communicator`, offering communication to the network,
    and on the other side handles simultaneously incoming messages.
    For that reason, the main part is in a separate thread.

    Call :meth:`.start_listen()` to actually listen.

    :param name: Name to listen under for control commands.
    :param int dataPort: Port number for the data protocol.
    :param heartbeat_interval: Interval between two heartbeats in s.
    :param context: zmq context.
    """

    def __init__(self,
                 name: str,
                 host: str = "localhost",
                 dataPort: int = 11099,
                 heartbeat_interval: float = 10,
                 context=None,
                 **kwargs) -> None:
        self.context = context or zmq.Context.instance()
        super().__init__(name=name, host=host, context=self.context, **kwargs)
        self.log.info(f"Start Listener for '{name}'.")
        self.host = host
        self.dataPort = dataPort
        pipe = self.context.socket(zmq.PAIR)
        pipe_port = pipe.bind_to_random_port("inproc://listenerPipe", min_port=12345)
        self.pipe = self.Pipe(pipe)
        self.pipeL = self.context.socket(zmq.PAIR)  # for the listening thread
        self.pipeL.connect(f"inproc://listenerPipe:{pipe_port}")
        self.heartbeat_interval = heartbeat_interval
        self._subscriptions: List[str] = []  # List of all subscriptions

        # Storage for returning asked messages
        self._buffer: List[Message] = []
        self._buffer_lock = Lock()
        self._event = Event()
        self.cids: List[bytes] = []  # List of conversation_ids of asked questions.

        self.rpc_generator = RPCGenerator()

    class Pipe:
        """Pipe endpoint with lock."""

        def __init__(self, socket, **kwargs) -> None:
            super().__init__(**kwargs)
            self.socket = socket
            self.lock = Lock()

        def send_multipart(self, frames: List[bytes] | Tuple[bytes, ...]) -> None:
            """Send a multipart message with frames (list type) ensuring lock."""
            self.lock.acquire()
            self.socket.send_multipart(frames)
            self.lock.release()

        def close(self, linger: float = 0) -> None:
            self.socket.close(linger)

    def publish_rpc_methods(self) -> None:
        super().publish_rpc_methods()
        self.rpc.method(self.subscribe)
        self.rpc.method(self.unsubscribe)
        self.rpc.method(self.unsubscribe_all)

    def close(self) -> None:
        """Close everything."""
        self.stop_listen()
        self.pipe.close(linger=1)
        self.pipeL.close(1)
        self.context.destroy(1)
        super().close()

    # Methods to control the Listener
    def stop_listen(self) -> None:
        """Stop the listener Thread."""
        try:
            if self.thread.is_alive():
                self.log.debug("Stopping listener thread.")
                self.pipe.send_multipart(frames=(b"STOP",))
                self.thread.join()
        except AttributeError:
            pass

    #   Control protocol
    def send(self, receiver: str | bytes, conversation_id: bytes = b"", data: object = None,
             **kwargs) -> None:
        """Send a message via control protocol."""
        self.pipe.send_multipart((b"SND", *compose_message(receiver=receiver, sender=self.full_name,
                                                           conversation_id=conversation_id,
                                                           data=data, **kwargs)))

    def send_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.full_name.encode()
        self.pipe.send_multipart((b"SND", *message.get_frames_list()))

    def reply(self, header: list, content: object) -> None:
        """Send a reply according to the original header frames and a content frame."""
        sender, conversation_id = header
        self.send(receiver=sender, conversation_id=conversation_id, data=content)

    def _check_message_in_buffer(self, conversation_id: bytes) -> Message | None:
        """Check the buffer for a message with the specified id."""
        with self._buffer_lock:
            for (i, message) in enumerate(self._buffer):
                if message.conversation_id == conversation_id:
                    del self._buffer[i]
                    return message
        return None

    def read_answer(self, conversation_id: bytes, tries: int = 10,
                    timeout: float = 0.1) -> Tuple[str, str, bytes, bytes, object]:
        """Read the answer of the original message with `conversation_id`."""
        # TODO deprecated?
        msg = self.read_answer_as_message(conversation_id=conversation_id, tries=tries,
                                          timeout=timeout)
        return self._turn_message_to_list(msg=msg)

    @staticmethod
    def _turn_message_to_list(msg: Message) -> Tuple[str, str, bytes, bytes, object]:
        """Turn a message into a list of often used parameters.

        :return: receiver, sender, conversation_id, message_id, data
        """
        # adding an empty byte for a faked message_id.
        return (msg.receiver.decode(), msg.sender.decode(), msg.conversation_id, b"",
                msg.data)

    def read_answer_as_message(self, conversation_id: bytes, tries: int = 10,
                               timeout: float = 0.1) -> Message:
        if (result := self._check_message_in_buffer(conversation_id=conversation_id)) is not None:
            return result
        for _ in range(tries):
            if self._event.wait(timeout):
                self._event.clear()
                if (result := self._check_message_in_buffer(conversation_id)) is not None:
                    return result
        # No result found:
        raise TimeoutError("Reading timed out.")

    def ask(self, receiver: bytes | str, conversation_id: Optional[bytes] = None, data=None,
            **kwargs) -> Message:
        if conversation_id is None:
            conversation_id = generate_conversation_id()
        if isinstance(receiver, str):
            receiver = receiver.encode()
        message = Message(receiver=receiver, conversation_id=conversation_id, data=data, **kwargs)
        return self.ask_message(message=message)

    ask_as_message = ask

    def ask_message(self, message: Message) -> Message:
        if not message.conversation_id:
            conversation_id = generate_conversation_id()
            header = create_header_frame(conversation_id=conversation_id,
                                         message_id=message.message_id)
            message.header = header
        self._event.clear()
        with self._buffer_lock:
            self.cids.append(message.conversation_id)
        self.send_message(message)
        return self.read_answer_as_message(conversation_id=message.conversation_id)

    def ask_rpc(self, receiver: bytes | str, method: str, **kwargs):
        string = self.rpc_generator.build_request_str(method=method, **kwargs)
        response = self.ask(receiver=receiver, data=string)
        return self.rpc_generator.get_result_from_response(response.payload[0])

    #   Data protocol
    def subscribe(self, topics: str | list | tuple) -> None:
        """Subscribe to a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self._subscribe(topic)
        else:
            self._subscribe(topics)

    def _subscribe(self, topic: str) -> None:
        if topic not in self._subscriptions:
            self.pipe.send_multipart((b"SUB", topic.encode()))
            self._subscriptions.append(topic)
        else:
            self.log.info(f"Already subscribed to {topic}.")

    def unsubscribe(self, topics: str | list | tuple) -> None:
        """Unsubscribe from a topic."""
        if isinstance(topics, (list, tuple)):
            for topic in topics:
                self._unsubscribe(topic)
        else:
            self._unsubscribe(topics)

    def _unsubscribe(self, topic: str) -> None:
        self.pipe.send_multipart((b"UNSUB", topic.encode()))
        if topic in self._subscriptions:
            del self._subscriptions[self._subscriptions.index(topic)]

    def unsubscribe_all(self) -> None:
        """Unsubscribe from all subscriptions."""
        while self._subscriptions:
            self._unsubscribe(self._subscriptions.pop())

    def heartbeat_timeout(self) -> None:
        """Cause a heartbeat."""
        self.pipe.send_multipart((b"HBT",))

    def rename(self, new_name: str) -> None:
        """Rename the listener to `new_name`."""
        self.pipe.send_multipart((b"REN", new_name.encode()))

    def start_listen(self, host: Optional[str] = None, dataPort: Optional[int] = None) -> None:
        """Start to listen in a thread.

        :param str host: Host name to listen to.
        :param int dataPort: Port for the subscription.
        """
        self.stop_listen()
        self.thread = Thread(
            target=self._listen,
            args=(self.context,
                  self.pipeL,
                  host or self.host,
                  dataPort or self.dataPort,
                  ))
        self.thread.daemon = True
        self.thread.start()

    """
    Methods below are executed in the thread, DO NOT CALL DIRECTLY!
    """

    def _listen(self, context, pipe, host: str, dataPort: int = 11099) -> None:
        """Listen on publisher - in another thread. Do not call directly."""
        self.log.info(f"Start listening, data port {host}:{dataPort}.")
        poller = zmq.Poller()
        subscriber = context.socket(zmq.SUB)
        subscriber.connect(f"tcp://{host}:{dataPort}")
        controller = self.socket
        # Poller setup
        poller.register(subscriber, zmq.POLLIN)
        poller.register(pipe, zmq.POLLIN)
        poller.register(controller, zmq.POLLIN)
        # Connect to Coordinator
        self.sign_in()
        heartbeat_timer = RepeatingTimer(interval=self.heartbeat_interval,
                                         function=self.heartbeat_timeout)
        heartbeat_timer.start()
        while True:
            socks = dict(poller.poll(1000))

            if pipe in socks:  # Internal communication.
                msg = pipe.recv_multipart()
                # HACK noq due to spyder "match"
                match msg:  # noqa
                    case [b"STOP"]:  # noqa: 211
                        self.log.debug("Stopping listening.")
                        break
                    case [b"SUB", topic]:  # noqa: 211
                        self.log.debug(f"Subscribing to {topic}.")
                        subscriber.subscribe(topic)
                    case [b"UNSUB", topic]:  # noqa: 211
                        self.log.debug(f"Unsubscribing from {topic}.")
                        subscriber.unsubscribe(topic)
                    case [b"SND", *message]:  # noqa: 211
                        self._send_frames(frames=message)
                    case [b"HBT"]:  # noqa: 211
                        self.heartbeat()
                    case [b"REN", new_name]:  # noqa: 211
                        self.sign_out()
                        self.name = new_name.decode()
                        self.sign_in()
                    case msg:
                        self.log.debug(f"Received unknown {msg}.")

            if subscriber in socks:  # Receiving regular data.
                try:
                    topic, content = subscriber.recv_multipart()
                except Exception as exc:
                    self.log.exception("Invalid data", exc)
                else:
                    try:
                        data = {topic.decode(): pickle.loads(content)}
                    except pickle.UnpicklingError:
                        try:
                            data = {topic.decode(): json.loads(content)}
                        except json.JSONDecodeError:
                            pass  # No valid data
                        else:
                            self.handle_subscription_data(data)
                    else:
                        self.handle_subscription_data(data)

            if controller in socks:  # Control
                self.handle_message()

        # Sign out from Coordinator
        heartbeat_timer.cancel()
        self.sign_out()

        # Close the connection.
        subscriber.close(1)
        self.log.info("Listening stopped.")

    # Data protocol
    def handle_subscription_data(self, data: dict) -> None:
        """Handle incoming subscription data."""
        raise NotImplementedError("Implement in subclass.")

    # Control protocol
    def _send_frames(self, frames):
        """Send frames over the connection."""
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def handle_commands(self, message: Message) -> None:
        """Handle commands: collect a requested response or give to :meth:`finish_handle_message`.

        :param str old_receiver: receiver frame.
        :param str old_sender: sender frame.
        :param str conversation_id: conversation_id.
        :param object data: deserialized data.
        """
        try:
            json = b"id" in message.payload[0] and (b"result" in message.payload[0]
                                                    or b"error" in message.payload[0])
        except (IndexError, KeyError):
            json = False
        if (message.conversation_id
                and message.conversation_id in self.cids
                and json):
            # give requested message to the calling application
            with self._buffer_lock:
                self._buffer.append(message)
                del self.cids[self.cids.index(message.conversation_id)]
            self._event.set()
        else:
            self.finish_handle_commands(message)

    def finish_handle_commands(self, message: Message) -> None:
        """Handle commands not requested via ask."""
        super().handle_commands(message)


class Republisher(BaseListener):
    """Listen on some values and republish a modified version.

    Call `listener.start_listen()` to actually listen.

    Republish values under a new name after having modified them.
    Time delay is around 1-2 ms.

    :param dict handlings: Dictionary with tuples of callable and new name.

    The following example takes the values of key 'old' and publishes the square
    of that value under the key 'new'. Wait until a KeyboardInterrupt (Ctrl+C) happens.

    .. code-block:: python

        def square(value):
            return value ** 2
        republisher = Republisher(handlings={'old': (square, "new")})
        republisher.start_listen()
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                break
    """

    def __init__(self, name: str = "Republisher", handlings: Optional[dict] = None,
                 *args, **kwargs):
        super().__init__(name, *args, **kwargs)
        self.publisher = Publisher()
        self.handlings = {} if handlings is None else handlings

    def start_listen(self, port: Optional[int] = None, **kwargs) -> None:
        super().start_listen(dataPort=port, **kwargs)
        for key in self.handlings.keys():
            self.subscribe(key)

    def handle_subscription_data(self, data: dict) -> None:
        """Call a calibration method and publish data under a new name."""
        new = {}
        if not isinstance(data, dict):
            self.log.error(f"{data} received, which is not a dictionary.")
        for key, value in data.items():
            if handling := self.handlings.get(key):
                try:
                    new[handling[1]] = handling[0](value)
                except Exception:
                    self.log.exception(f"Handling of '{key}' failed.")
        if new:
            self.publisher(new)
