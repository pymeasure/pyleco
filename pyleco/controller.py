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

from pyleco.publisher import Publisher
from pyleco.utils import (Commands, compose_message, divide_message, interpret_header,
                          deserialize_data, split_name,
                          )
from pyleco.timers import RepeatingTimer

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


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
    """Maintain connection to the router and listen to incoming messages.

    :param str name: Name to listen to and to publish values with.
    :param int port: Port number to connect to.
    :param protocol: Connection protocol.
    """

    def __init__(self, name, host="localhost", port=12300, protocol="tcp",
                 context=zmq.Context.instance(),
                 **kwargs):
        self.name = name
        self.node = None

        # ZMQ setup
        self.socket = context.socket(zmq.DEALER)
        self.socket.connect(f"{protocol}://{host}:{port}")

        super().__init__(**kwargs)  # for cooperation

    def listen(self, stop_event=InfiniteEvent(), waiting_time=100):
        """Listen for zmq communication until `stop_event` is set.

        :param waiting_time: Time to wait for a readout signal in ms.
        """
        log.info(f"Start to listen as '{self.name}'.")
        self.stop_event = stop_event
        # Prepare
        poller = zmq.Poller()
        poller.register(self.socket, zmq.POLLIN)

        # open communication
        self.send("COORDINATOR", data=[[Commands.SIGNIN]])
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
        log.info(f"Stop listen as '{self.name}'.")
        self.send("COORDINATOR", data=[[Commands.SIGNOUT]])
        self.handle_message()

    def heartbeat(self):
        """Send a heartbeat to the router."""
        self.send("COORDINATOR")
        log.debug("heartbeating")

    def _send(self, frames):
        """Send frames over the connection."""
        self.socket.send_multipart(frames)

    def send(self, receiver, sender=None, conversation_id="", message_id="", data=None,
             receiver_mid=None, sender_mid=None):
        """Send a message to a receiver with serializable `data`."""
        if receiver_mid:
            conversation_id = receiver_mid
        if sender_mid:
            message_id = sender_mid
        if sender is None:
            sender = ".".join((self.node, self.name)) if self.node else self.name
        self._send(compose_message(
            receiver=receiver, sender=sender, conversation_id=conversation_id,
            message_id=message_id, data=data))

    def send_reply(self, receiver, data, message_id=None, old_header=None):
        """Send a reply according to the received header.

        :param receiver: Name of the receiver.
        :param data: data to send.
        :param message_id: Sender message id. Timestamp if not specified.
        :param old_header: Originally received header frame.
        """
        if message_id is None:
            message_id = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M:%S.%f")
        conversation_id, sender_message_id = interpret_header(old_header)
        self.send(receiver, conversation_id=conversation_id, message_id=message_id,
                  data=data)

    def handle_message(self):
        """Interpret incoming message."""
        msg = self.socket.recv_multipart()
        version, old_receiver, old_sender, old_header, payload = divide_message(msg)
        if payload:
            data = deserialize_data(payload[0])
        else:
            return
        s_node, s_name = split_name(old_sender)
        if s_name == b"COORDINATOR":
            log.warning(f"Message from the Coordinator: '{data}'")
            for message in data:
                if message == [Commands.ERROR, "You did not sign in!"]:
                    self.node = None
                    self.send("COORDINATOR", data=[[Commands.SIGNIN]])
                elif self.node is None and message[0] == Commands.ACKNOWLEDGE:
                    self.node = s_node.decode()
                    log.info(f"Signed in to Node '{self.node}'.")
            return
        self.handle_commands(old_receiver, old_sender, old_header, data)

    def handle_commands(self, old_receiver, old_sender, old_header, data):
        """Handle the list of commands."""
        reply = []
        if isinstance(data, (list, tuple)):
            for message in data:
                if message[0] == Commands.OFF:
                    reply.append([Commands.ACKNOWLEDGE])
                    self.stop_event.set()
                else:
                    reply.append(self.handle_command(*message))
            self.send_reply(receiver=old_sender, old_header=old_header, data=reply)
        else:
            log.warning(f"Unknown message received: '{data}'.")

    def handle_command(self, command, content=None):
        """Handle a command with optional content.

        :param command: Command
        :param content: Content for the command.
        :return: Response to send to the requester.
        """
        raise NotImplementedError("Implement in subclass.")


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
        return Commands.ACKNOWLEDGE, self.get_properties(properties)

    def _set_properties(self, properties):
        """Internal method, includes response Command type."""
        try:
            self.set_properties(properties)
        except Exception as exc:
            log.exception("Setting properties failed", exc_info=exc)
            return Commands.ERR, (properties, str(exc))
        else:
            return Commands.ACKNOWLEDGE

    def _call(self, content):
        """Internal method, includes response Command type."""
        method = content.pop("_name")
        args = content.pop("_args", ())
        try:
            value = self.call(method, args, content)
        except Exception as exc:
            return Commands.ERROR, [type(exc).__name__, str(exc)]
        else:
            return Commands.ACKNOWLEDGE, value

    def get_properties(self, properties):
        """Get properties from the list `properties`."""
        data = {}
        for key in properties:
            data[key] = getattr(self, key)
        return data

    def set_properties(self, properties):
        """Set properties from a dictionary."""
        for key, value in properties.items():
            setattr(self, key, value)

    def call(self, method, args, kwargs):
        """Call a method with arguments dictionary `kwargs`."""
        return getattr(self, method)(*args, **kwargs)


class InstrumentController(BaseController):
    """Control an instrument listening to zmq messages and regular readout.

    .. code::

        c = InstrumentController("testing", TestClass, auto_connect={'COM': 5})
        c._readout = readout  # some function readout(device, publisher)
        c.start_timer()
        c.listen()  # here everything happens until told to stop from elsewhere
        c.disconnect()


    :param str name: Name to listen to and to publish values with.
    :param class cls: Instrument class.
    :param int port: Port number to connect to.
    :param periodic_reading: Inteval between periodic readouts in s.
    :param dict auto_connect: Kwargs to automatically connect to the device.
    :param \\**kwargs: Keywoard arguments for the general message handling.
    """

    def __init__(self, name, cls, periodic_reading=1, auto_connect=False,
                 context=zmq.Context.instance(),
                 **kwargs):
        super().__init__(name, context=context, **kwargs)
        self.cls = cls

        # Pipe for the periodic readout timer
        self.pipe = context.socket(zmq.PAIR)
        self.pipe.set_hwm(1)
        pipe_port = self.pipe.bind_to_random_port("inproc://listenerPipe", min_port=12345)
        self.pipeL = context.socket(zmq.PAIR)
        self.pipeL.set_hwm(1)
        self.pipeL.connect(f"inproc://listenerPipe:{pipe_port}")

        self.timer = RepeatingTimer(periodic_reading, self.queue_readout)
        self.publisher = Publisher(log=log)

        if auto_connect:
            self.connect(**auto_connect)
        log.info(f"InstrumentController '{name}' initialized.")

    def __del__(self):
        self.disconnect()

    def listen(self, stop_event=InfiniteEvent(), waiting_time=100):
        """Listen for zmq communication until `stop_event` is set.

        :param waiting_time: Time to wait for a readout signal in ms.
        """
        log.info("Start to listen.")
        self.stop_event = stop_event
        # Prepare
        poller = zmq.Poller()
        poller.register(self.pipeL, zmq.POLLIN)
        poller.register(self.socket, zmq.POLLIN)

        # Open communication
        self.send("COORDINATOR", data=[[Commands.SIGNIN]])
        next_beat = time.perf_counter() + heartbeat_interval
        # Loop
        while not stop_event.is_set():
            socks = dict(poller.poll(waiting_time))
            if self.pipeL in socks:
                self.pipeL.recv()
                self.readout()
            if self.socket in socks:
                self.handle_message()
            elif (now := time.perf_counter()) > next_beat:
                self.heartbeat()
                next_beat = now + heartbeat_interval
        # Close
        self.disconnect()
        self.send("COORDINATOR", data=[[Commands.SIGNOUT]])
        self.handle_message()

    def queue_readout(self):
        self.pipe.send(b"")

    def publish(self, data):
        """Publish `data` over the data channel."""
        self.publisher.send(data)

    def _call(self, content):
        method = content.pop("_name")
        args = content.pop("_args", ())
        if method:
            value = getattr(self.device, method)(*args, **content)
        else:
            method = content.pop("_controller")
            if method:
                value = getattr(self, method)(*args, **content)
        return Commands.CALL, value

    def _readout(self, device, publisher):
        raise NotImplementedError("Implement in subclass")

    def readout(self):
        """Do periodic readout of the instrument and publish the data."""
        self._readout(self.device, self.publisher)

    def start_timer(self):
        """Start the timer."""
        try:
            self.timer.start()
        except RuntimeError:
            self.timer = RepeatingTimer(self.timer.interval, self.queue_readout)
            self.timer.start()

    def stop_timer(self):
        """Stop the timer."""
        self.timer.cancel()

    @property
    def timeout(self):
        """Timeout interval of the timer in ms."""
        return self.timer.interval

    @timeout.setter
    def timeout(self, value):
        self.timer.interval = value

    def connect(self, *args, **kwargs):
        """Connect to the device."""
        # TODO read auto_connect?
        log.info("Connecting")
        self.device = self.cls(*args, **kwargs)
        self.start_timer()

    def disconnect(self):
        """Disconnect the device."""
        log.info("Disconnecting.")
        self.stop_timer()
        try:
            self.device.shutdown()
        except AttributeError:
            pass
        try:
            del self.device
        except AttributeError:
            pass

    def get_properties(self, properties):
        """Get properties from the list `properties`."""
        data = {}
        # if "_controller" in properties:
        #     properties.pop(properties.index("_controller"))
        #     data["_controller"] = c_data = {}
        #     for key in c_props:  # dictionary for the controller itself
        #         c_data[key] = getattr(self, key)
        for key in properties:
            data[key] = getattr(self.device, key)
        return data

    def set_properties(self, properties):
        """Set properties from a dictionary."""
        # if c_props := properties.pop("_controller", None):
        #     for key, value in c_props:  # for the controller itself
        #         setattr(self, key, value)
        for key, value in properties.items():
            setattr(self.device, key, value)

    def call(self, method, args, kwargs):
        """Call a method with arguments dictionary `kwargs`."""
        if method == "_controller":
            method = kwargs.pop("_controller")
            return getattr(self, method)(*args, **kwargs)
        return getattr(self.device, method)(*args, **kwargs)
