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

import time

import zmq

from .controller import BaseController, InfiniteEvent, heartbeat_interval
from .publisher import Publisher
from .timers import RepeatingTimer
from .utils import Commands


class Actor(BaseController):
    """Control an instrument listening to zmq messages and regularly read the some values.

    .. code::

        c = InstrumentController("testing", TestClass, auto_connect={'COM': 5})
        c._readout = readout  # some function readout(device, publisher)
        c.start_timer()
        c.listen(stop_event)  # here everything happens until told to stop from elsewhere
        c.disconnect()


    :param str name: Name to listen to and to publish values with.
    :param class cls: Instrument class.
    :param int port: Port number to connect to.
    :param periodic_reading: Inteval between periodic readouts in s.
    :param dict auto_connect: Kwargs to automatically connect to the device.
    :param \\**kwargs: Keywoard arguments for the general message handling.
    """

    def __init__(self, name, cls, periodic_reading=-1, auto_connect=False,
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
        self.publisher = Publisher(log=self.root_logger)

        if auto_connect:
            self.connect(**auto_connect)
        self.log.info(f"InstrumentController '{name}' initialized.")

    def __del__(self):
        self.disconnect()

    def __exit__(self, *args, **kwargs):
        self.disconnect()
        super().__exit__(*args, **kwargs)

    def listen(self, stop_event=InfiniteEvent(), waiting_time=100):
        """Listen for zmq communication until `stop_event` is set.

        :param waiting_time: Time to wait for a readout signal in ms.
        """
        self.log.info("Start to listen.")
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

    def _readout(self, device, publisher):
        raise NotImplementedError("Implement in subclass")

    def readout(self):
        """Do periodic readout of the instrument and publish the data."""
        self._readout(self.device, self.publisher)

    def start_timer(self, interval=None):
        """Start the readout timer."""
        if interval is not None:
            self.timer.interval = interval
        if self.timer.interval < 0:
            return
        try:
            self.timer.start()
        except RuntimeError:
            self.timer = RepeatingTimer(self.timer.interval, self.queue_readout)
            self.timer.start()

    def stop_timer(self):
        """Stop the readout timer."""
        self.timer.cancel()

    @property
    def timeout(self):
        """Timeout interval of the readout timer in s."""
        return self.timer.interval

    @timeout.setter
    def timeout(self, value):
        self.timer.interval = value

    def connect(self, *args, **kwargs):
        """Connect to the device."""
        # TODO read auto_connect?
        self.log.info("Connecting")
        self.device = self.cls(*args, **kwargs)
        self.start_timer()

    def disconnect(self):
        """Disconnect the device."""
        self.log.info("Disconnecting.")
        self.stop_timer()
        try:
            self.device.adapter.close()
        except AttributeError:
            pass
        try:
            del self.device
        except AttributeError:
            pass

    def get_properties(self, properties):
        """Get properties from the list `properties`."""
        data = {}
        if properties[0] == "_actor":
            return super().get_properties(properties[1:])
        for key in properties:
            data[key] = v = getattr(self.device, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_properties(self, properties):
        """Set properties from a dictionary."""
        for key, value in properties.items():
            if key == "_actor":
                super().set_properties(value)
            else:
                setattr(self.device, key, value)

    def call(self, method, args, kwargs):
        """Call a method with arguments dictionary `kwargs`."""
        if method == "_actor":
            method = kwargs.pop("_actor")
            return super().call(method, args, kwargs)
        return getattr(self.device, method)(*args, **kwargs)
