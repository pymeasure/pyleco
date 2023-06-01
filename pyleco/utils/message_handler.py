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
from typing import Optional

import zmq

from ..core.message import Message
from ..core.enums import Commands, Errors
from ..core.serialization import compose_message
from .zmq_log_handler import ZmqLogHandler


# Parameters
heartbeat_interval = 10  # s


class InfiniteEvent:
    def __init__(self):
        self._flag = False

    def is_set(self):
        return self._flag

    def set(self):
        self._flag = True


class MessageHandler:
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
                 log=None,
                 context=None,
                 **kwargs):
        self.name = name
        self.node: None | str = None
        self.full_name = name
        context = context or zmq.Context.instance()

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

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.close()

    def close(self):
        """Close the connection."""
        self.socket.close(1)

    # Base communication
    def sign_in(self):
        self._send_final_message(Message(b"COORDINATOR", data=[[Commands.SIGNIN]]))

    def heartbeat(self):
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self._send_final_message(Message(b"COORDINATOR"))

    def sign_out(self):
        self._send_final_message(Message(b"COORDINATOR", data=[[Commands.SIGNOUT]]))

    def _send_frames(self, frames):
        """Send frames over the connection."""
        # TODO deprecated
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _send_final_message(self, message: Message) -> None:
        if not message.sender:
            message.sender = self.full_name.encode()
        frames = message.get_frames_list()
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _compose_message(self, receiver, sender=None, data=None, conversation_id=b"",
                         **kwargs) -> list:
        if sender is None:
            sender = self.full_name
        # TODO decide on timestamp
        # if message_id == None:
        #     message_id = datetime.datetime.now(datetime.timezone.utc).strftime(
        #                                                           "%H:%M:%S.%f").encode()
        try:
            msg = compose_message(receiver=receiver, sender=sender,
                                  conversation_id=conversation_id, data=data,
                                  **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            msg = compose_message(receiver, sender, conversation_id=conversation_id,
                                  data=[[Commands.ERROR, Errors.EXECUTION_FAILED,
                                         type(exc).__name__, str(exc)]])
        return msg

    def _send(self, receiver, sender=None, data=None, conversation_id=b"", **kwargs):
        """Compose and send a message to a `receiver` with serializable `data`."""
        frames = self._compose_message(receiver, sender, data, conversation_id, **kwargs)
        message = Message.from_frames(*frames)
        self._send_final_message(message)

    # User commands
    def send(self, receiver, data=None, conversation_id=b"", **kwargs):
        """Send a message to a receiver with serializable `data`."""
        self._send(receiver=receiver, data=data, conversation_id=conversation_id, **kwargs)

    def send_message(self, message: Message) -> None:
        self._send_final_message(message)

    # Continuous listening and message handling
    def listen(self, stop_event=InfiniteEvent(), waiting_time=100):
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
            pass
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
        if msg.data is None:
            return
        if msg.sender_name == b"COORDINATOR" and isinstance(msg.data, (tuple, list)):
            for message in msg.data:
                if message == [Commands.ERROR, Errors.NOT_SIGNED_IN]:
                    self.node = None
                    self.full_name = self.name
                    try:
                        del self.logHandler.fullname
                    except AttributeError:
                        pass  # already deleted.
                    self.sign_in()
                    self.log.warning("I was not signed in, signing in.")
                    return
                elif self.node is None and message[0] == Commands.ACKNOWLEDGE:
                    self.node = msg.sender_node.decode()
                    self.full_name = ".".join((self.node, self.name))
                    try:
                        self.logHandler.fullname = self.full_name
                    except AttributeError:
                        pass
                    self.log.info(f"Signed in to Node '{self.node}'.")
                    return
                elif message == [Commands.PING]:
                    self.heartbeat()
                    return
                elif message == [Commands.ERROR, Errors.DUPLICATE_NAME]:
                    self.log.warning("Sign in failed, the name is already used.")
                    return
            self.log.warning(f"Message from the Coordinator: '{msg.data}'")
        self.handle_commands(msg)

    def handle_commands(self, msg: Message):
        """Handle the list of commands.

        :param str old_receiver: receiver frame.
        :param str old_sender: sender frame.
        :param str conversation_id: conversation_id.
        :param object data: deserialized data.
        """
        reply = []
        if isinstance(msg.data, (list, tuple)):
            for message in msg.data:
                if message[0] == Commands.OFF:
                    reply.append([Commands.ACKNOWLEDGE])
                    self.stop_event.set()
                elif message[0] == Commands.LOG:
                    try:
                        self.root_logger.setLevel(message[1])
                    except Exception as exc:
                        reply.append([Commands.ERROR, Errors.EXECUTION_FAILED,
                                      type(exc).__name__, str(exc)])
                    else:
                        reply.append([Commands.ACKNOWLEDGE])
                elif message[0] == Commands.PING:
                    pass  # empty message
                else:
                    reply.append(self.handle_command(*message))
            self.handle_reply(original_message=msg, reply=reply)
        else:
            self.log.warning(f"Unknown message received: '{msg.data}'.")

    def handle_command(self, command, content=None):
        """Handle a command with optional content.

        :param command: Command
        :param content: Content for the command.
        :return: Response to send to the requester.
        """
        raise NotImplementedError("Implement in subclass.")

    def handle_reply(self, original_message: Message, reply: list) -> None:
        """Handle the created reply."""
        response = Message(receiver=original_message.sender,
                           conversation_id=original_message.conversation_id,
                           data=reply)
        self.send_message(message=response)


class BaseController(MessageHandler):
    """Control something, allow to get/set properties and call methods."""

    def handle_command(self, command: str, content: Optional[object] = None) -> tuple:
        """Handle commands."""
        # HACK noqa while flake does not recognize "match"
        match command:  # noqa
            case Commands.GET:
                return self._get_properties(content)
            case Commands.SET:
                return self._set_properties(content)
            case Commands.CALL:
                return self._call(content)
            case _:
                return ()

    def _get_properties(self, properties: list | tuple) -> tuple:
        """Internal method, includes response Command type."""
        # TODO error handling
        try:
            return Commands.ACKNOWLEDGE, self.get_properties(properties)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)

    def _set_properties(self, properties: dict) -> tuple:
        """Internal method, includes response Command type."""
        try:
            self.set_properties(properties)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            self.log.exception("Setting properties failed", exc_info=exc)
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)
        else:
            return Commands.ACKNOWLEDGE,

    def _call(self, content: dict):
        """Internal method, includes response Command type."""
        method = content.pop("_name")
        args = content.pop("_args", ())
        try:
            return Commands.ACKNOWLEDGE, self.call(method, args, content)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)

    def get_properties(self, properties: list | tuple) -> dict:
        """Get properties from the list `properties`."""
        data = {}
        for key in properties:
            data[key] = v = getattr(self, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_properties(self, properties: dict) -> None:
        """Set properties from a dictionary."""
        for key, value in properties.items():
            setattr(self, key, value)

    def call(self, method, args, kwargs):
        """Call a method with arguments dictionary `kwargs`."""
        return getattr(self, method)(*args, **kwargs)
