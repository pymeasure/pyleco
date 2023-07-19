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
from typing import Any, Callable, Optional, Union

import zmq

from ..utils.message_handler import BaseController, InfiniteEvent, heartbeat_interval, Event
from ..utils.publisher import Publisher
from ..utils.timers import RepeatingTimer


class Actor(BaseController):
    """Control an instrument listening to zmq messages and regularly read some values.

    .. code::

        a = Actor("testing", TestClass)
        # define some function `readout(device: Instrument, publisher: Publisher)`
        a.read_publish = readout
        a.connect("COM5")  # connect to device
        # in listen everything happens until told to stop from elsewhere
        a.listen(stop_event)
        a.disconnect()

    Like the :class:`MessageHandler`, this class can be used as a context manager disconnecting at
    the end of the context.

    :param str name: Name to listen to and to publish values with.
    :param class cls: Instrument class.
    :param int port: Port number to connect to.
    :param periodic_reading: Inteval between periodic readouts in s.
    :param dict auto_connect: Kwargs to automatically connect to the device.
    :param \\**kwargs: Keywoard arguments for the general message handling.
    """

    def __init__(self, name: str, cls, periodic_reading: float = -1,
                 auto_connect: Optional[dict] = None,
                 context: Optional[zmq.Context] = None,
                 **kwargs):
        context = context or zmq.Context.instance()
        super().__init__(name=name, context=context, **kwargs)
        self.cls = cls

        # Pipe for the periodic readout timer
        self.pipe = context.socket(zmq.PAIR)
        self.pipe.set_hwm(1)
        pipe_port = self.pipe.bind_to_random_port("inproc://listenerPipe", min_port=12345)
        self.pipeL = context.socket(zmq.PAIR)
        self.pipeL.set_hwm(1)
        self.pipeL.connect(f"inproc://listenerPipe:{pipe_port}")

        self.timer = RepeatingTimer(interval=periodic_reading, function=self.queue_readout)
        self.publisher = Publisher(log=self.root_logger)

        if auto_connect:
            self.connect(**auto_connect)
        self.log.info(f"Actor '{name}' initialized.")

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.rpc.method(self.start_polling)
        self.rpc.method(self.stop_polling)
        self.rpc.method(self.get_polling_interval)
        self.rpc.method(self.set_polling_interval)
        self.rpc.method(self.connect)
        self.rpc.method(self.disconnect)
        # TODO decide how to call the actor and how to call the device?

    def register_device_method(self, method: Callable):
        name = method.__name__
        self.rpc.method(method, name="device." + name)

    def __del__(self) -> None:
        self.disconnect()

    def __exit__(self, *args, **kwargs) -> None:
        super().__exit__(*args, **kwargs)
        self.disconnect()

    def listen(self, stop_event: Event = InfiniteEvent(), waiting_time: int = 100) -> None:
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
        self.sign_in()
        next_beat = time.perf_counter() + heartbeat_interval
        # Loop
        while not stop_event.is_set():
            socks = dict(poller.poll(timeout=waiting_time))
            if self.pipeL in socks:
                self.pipeL.recv()
                self.readout()
            if self.socket in socks:
                self.handle_message()
            elif (now := time.perf_counter()) > next_beat:
                self.heartbeat()
                next_beat = now + heartbeat_interval
        # Close
        self.sign_out()
        self.handle_message()

    def queue_readout(self) -> None:
        self.pipe.send(b"")

    def publish(self, data: Any) -> None:
        """Publish `data` over the data channel."""
        self.publisher.send(data=data)

    def _readout(self, device, publisher) -> None:
        """Deprecated, use `read_publish` instead."""
        pass

    def read_publish(self, device, publisher: Publisher) -> None:
        """Read the device and publish the results.

        Defaults to doing nothing. Implement in a subclass.
        """
        # TODO keep temporarily for backward compatibility
        self._readout(device=device, publisher=publisher)
        pass

    def readout(self) -> None:
        """Do periodic readout of the instrument and publish the data.

        Defaults to calling :meth:`read_publish` with the device and publisher as arguments.
        """
        self.read_publish(device=self.device, publisher=self.publisher)

    def start_timer(self, interval: Optional[float] = None) -> None:
        """Start the readout timer."""
        if interval is not None:
            self.timer.interval = interval
        if self.timer.interval < 0:
            return
        try:
            self.timer.start()
        except RuntimeError:
            self.timer = RepeatingTimer(interval=self.timer.interval, function=self.queue_readout)
            self.timer.start()

    def stop_timer(self) -> None:
        """Stop the readout timer."""
        self.timer.cancel()

    def start_polling(self, polling_interval: Optional[float] = None) -> None:
        self.start_timer(interval=polling_interval)

    def stop_polling(self) -> None:
        self.stop_timer()

    @property
    def polling_interval(self) -> float:
        """Timeout interval of the readout timer in s."""
        return self.timer.interval

    @polling_interval.setter
    def polling_interval(self, value: float) -> None:
        self.timer.interval = value

    def get_polling_interval(self) -> float:
        return self.polling_interval

    def set_polling_interval(self, polling_interval: float) -> None:
        self.polling_interval = polling_interval

    def connect(self, *args, **kwargs) -> None:
        """Connect to the device."""
        # TODO read auto_connect?
        self.log.info("Connecting")
        self.device = self.cls(*args, **kwargs)
        self.start_timer()

    def disconnect(self) -> None:
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

    def get_parameters(self, parameters: Union[list[str], tuple[str, ...]]) -> dict[str, Any]:
        """Get properties from the list `properties`."""
        data = {}
        if parameters[0] == "_actor":
            return super().get_parameters(parameters[1:])
        for key in parameters:
            data[key] = v = getattr(self.device, key)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
        return data

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        """Set properties from a dictionary."""
        for key, value in parameters.items():
            if key == "_actor":
                super().set_parameters(value)
            else:
                setattr(self.device, key, value)

    def call_action(self, action: str, _args: Optional[list | tuple] = None, **kwargs) -> Any:
        """Call a method with arguments dictionary `kwargs`."""
        if _args is None:
            _args = ()
        if action == "_actor":
            action = kwargs.pop("_actor")
            return super().call_action(action=action, _args=_args, kwargs=kwargs)
        return getattr(self.device, action)(*_args, **kwargs)