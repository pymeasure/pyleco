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
import datetime
import time

import zmq

from .publisher import Publisher
from .utils import (Commands, compose_message, divide_message, interpret_header,
                    deserialize_data, split_name, split_name_str, split_message,
                    Errors,
                    )
from .timers import RepeatingTimer
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

    You may use it as a context manager.

    :param str name: Name to listen to and to publish values with.
    :param int port: Port number to connect to.
    :param protocol: Connection protocol.
    :param log: Logger instance whose logs should be published. Defaults to "__main__".
    """

    def __init__(self, name, host="localhost", port=12300, protocol="tcp",
                 log=None,
                 context=None,
                 **kwargs):
        self.name = name
        self.node = None
        self.fname = name
        context = context or zmq.Context.instance()

        self.logHandler = ZmqLogHandler()
        if log is None:
            log = logging.getLogger("__main__")
        # Add the ZmqLogHandler to the root logger, unless it has already a Handler.
        first_pub_handler = True  # we expect to be the first ZmqLogHandler
        for h in log.handlers:
            if isinstance(h, ZmqLogHandler):
                first_pub_handler = False
                break
        if first_pub_handler:
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
        """Close the connection on closing."""
        self.socket.close(1)

    # Base communication
    def sign_in(self):
        self._send("COORDINATOR", data=[[Commands.SIGNIN]])

    def heartbeat(self):
        """Send a heartbeat to the router."""
        self.log.debug("heartbeat")
        self._send("COORDINATOR")

    def sign_out(self):
        self._send("COORDINATOR", data=[[Commands.SIGNOUT]])

    def _send_frames(self, frames):
        """Send frames over the connection."""
        self.log.debug(f"Sending {frames}")
        self.socket.send_multipart(frames)

    def _send(self, receiver, sender=None, data=None, conversation_id=b"", **kwargs):
        """Compose and send a message to a `receiver` with serializable `data`."""
        if sender is None:
            sender = self.fname
        # TODO decide on timestamp
        # if message_id == None:
        #     message_id = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f").encode()
        try:
            msg = compose_message(receiver=receiver, sender=sender,
                                  conversation_id=conversation_id, data=data,
                                  **kwargs)
        except Exception as exc:
            self.log.exception(f"Composing message with data {data} failed.", exc_info=exc)
            self._send(receiver, sender, conversation_id=conversation_id,
                       data=[[Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)]])
        else:
            self._send_frames(msg)

    # User commands
    def send(self, receiver, data=None, conversation_id=b"", **kwargs):
        """Send a message to a receiver with serializable `data`."""
        self._send(receiver=receiver, data=data, conversation_id=conversation_id, **kwargs)

    # Continuous listening and message handling
    def listen(self, stop_event=InfiniteEvent(), waiting_time=100):
        """Listen for zmq communication until `stop_event` is set.

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
        while not stop_event.is_set():
            socks = dict(poller.poll(waiting_time))
            if self.socket in socks:
                self.handle_message()
            elif (now := time.perf_counter()) > next_beat:
                self.heartbeat()
                next_beat = now + heartbeat_interval
        # Close
        self.log.info(f"Stop listen as '{self.name}'.")
        self.sign_out()
        self.handle_message()

    def handle_message(self):
        """Interpret incoming message.

        COORDINATOR messages are handled and then :meth:`handle_commands` does the rest.
        """
        msg = self.socket.recv_multipart()
        self.log.debug(f"Handling {msg}")
        old_receiver, old_sender, conversation_id, message_id, data = split_message(msg)
        if data is None:
            return
        s_node, s_name = split_name_str(old_sender)
        if s_name == "COORDINATOR":
            for message in data:
                if message == [Commands.ERROR, Errors.NOT_SIGNED_IN]:
                    self.node = None
                    self.fname = self.name
                    try:
                        del self.logHandler.fullname
                    except AttributeError:
                        pass  # already deleted.
                    self.sign_in()
                    self.log.warning("I was not signed in, signing in.")
                    return
                elif self.node is None and message[0] == Commands.ACKNOWLEDGE:
                    self.node = s_node
                    self.fname = ".".join((self.node, self.name))
                    self.logHandler.fullname = self.fname
                    self.log.info(f"Signed in to Node '{self.node}'.")
                    return
                elif message == [Commands.PING]:
                    self.heartbeat()
                    return
                elif message == [Commands.ERROR, Errors.DUPLICATE_NAME]:
                    self.log.warning("Sign in failed, the name is already used.")
                    return
            self.log.warning(f"Message from the Coordinator: '{data}'")
        self.handle_commands(old_receiver, old_sender, conversation_id, data)

    def handle_commands(self, old_receiver, old_sender, conversation_id, data):
        """Handle the list of commands.

        :param str old_receiver: receiver frame.
        :param str old_sender: sender frame.
        :param str conversation_id: conversation_id.
        :param object data: deserialized data.
        """
        reply = []
        if isinstance(data, (list, tuple)):
            for message in data:
                if message[0] == Commands.OFF:
                    reply.append([Commands.ACKNOWLEDGE])
                    self.stop_event.set()
                elif message[0] == Commands.LOG:
                    try:
                        self.root_logger.setLevel(message[1])
                    except Exception as exc:
                        reply.append([Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)])
                    else:
                        reply.append([Commands.ACKNOWLEDGE])
                elif message[0] == Commands.PING:
                    pass  # empty message
                else:
                    reply.append(self.handle_command(*message))
            self.handle_reply(old_sender, conversation_id, reply)
        else:
            self.log.warning(f"Unknown message received: '{data}'.")

    def handle_command(self, command, content=None):
        """Handle a command with optional content.

        :param command: Command
        :param content: Content for the command.
        :return: Response to send to the requester.
        """
        raise NotImplementedError("Implement in subclass.")

    def handle_reply(self, old_sender, conversation_id, reply):
        """Handle the created reply."""
        self.send(receiver=old_sender, conversation_id=conversation_id, data=reply)


class BaseController(MessageHandler):
    """Control something, allow to get/set properties and call methods."""

    def handle_command(self, command, content=None):
        """Handle commands."""
        # HACK noqa while flake does not recognize "match"
        match command:  # noqa
            case Commands.GET:
                return self._get_properties(content)
            case Commands.SET:
                return self._set_properties(content)
            case Commands.CALL:
                return self._call(content)

    def _get_properties(self, properties):
        """Internal method, includes response Command type."""
        # TODO error handling
        try:
            return Commands.ACKNOWLEDGE, self.get_properties(properties)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)

    def _set_properties(self, properties):
        """Internal method, includes response Command type."""
        try:
            self.set_properties(properties)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            self.log.exception("Setting properties failed", exc_info=exc)
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)
        else:
            return Commands.ACKNOWLEDGE

    def _call(self, content):
        """Internal method, includes response Command type."""
        method = content.pop("_name")
        args = content.pop("_args", ())
        try:
            return Commands.ACKNOWLEDGE, self.call(method, args, content)
        except AttributeError as exc:
            return Commands.ERROR, Errors.NAME_NOT_FOUND, str(exc)
        except Exception as exc:
            return Commands.ERROR, Errors.EXECUTION_FAILED, type(exc).__name__, str(exc)

    def get_properties(self, properties):
        """Get properties from the list `properties`."""
        data = {}
        for key in properties:
            data[key] = v = getattr(self, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_properties(self, properties):
        """Set properties from a dictionary."""
        for key, value in properties.items():
            setattr(self, key, value)

    def call(self, method, args, kwargs):
        """Call a method with arguments dictionary `kwargs`."""
        return getattr(self, method)(*args, **kwargs)


from .actor import Actor as InstrumentController
