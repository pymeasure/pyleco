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

from typing import Any, Callable, Generic, Optional, Sequence, TypeVar, Union
from warnings import warn

import zmq

from ..utils.message_handler import MessageHandler
from ..utils.data_publisher import DataPublisher
from ..utils.timers import RepeatingTimer


Device = TypeVar("Device")


class Actor(MessageHandler, Generic[Device]):
    """Control an instrument listening to zmq messages and regularly read some values.

    .. code::

        a = Actor("testing", TestClass)
        # define some function `readout(device: Device, publisher: DataPublisher)`
        a.read_publish = readout
        a.connect("COM5")  # connect to device
        # in listen everything happens until told to stop from elsewhere
        a.listen(stop_event)
        a.disconnect()

    Like the :class:`MessageHandler`, this class can be used as a context manager disconnecting at
    the end of the context.

    The (via RPC available) methods :meth:`get_parameters`, :meth:`set_parameters`, and
    :meth:`call_action` get/set parameters of the device or call an action of the device.
    You can also register device methods with :meth:`register_device_method`, such that this method
    is available via RPC as well.

    :param str name: Name to listen to and to publish values with.
    :param class device_class: Instrument class.
    :param int port: Port number to connect to.
    :param periodic_reading: Interval between periodic readouts in s.
    :param dict auto_connect: Kwargs to automatically connect to the device.
    :param class cls: See :code:`device_class`.

        .. deprecated:: 0.3
            Deprecated, use :code:`device_class` instead.

    :param \\**kwargs: Keywoard arguments for the general message handling.
    """

    device: Device

    def __init__(
        self,
        name: str,
        device_class: Optional[type[Device]] = None,
        periodic_reading: float = -1,
        auto_connect: Optional[dict] = None,
        context: Optional[zmq.Context] = None,
        cls: Optional[type[Device]] = None,
        **kwargs,
    ):
        context = context or zmq.Context.instance()
        super().__init__(name=name, context=context, **kwargs)
        if cls is not None:
            warn("Parameter `cls` is deprecated, use `device_class` instead.", FutureWarning)
            device_class = cls
        if device_class is None:
            # Keep this check as long as device_class is optional due to deprecated cls parameter
            raise ValueError("You have to specify a `device_class`!")
        self.device_class = device_class

        # Pipe for the periodic readout timer
        self.pipe: zmq.Socket = context.socket(zmq.PAIR)
        self.pipe.set_hwm(1)
        pipe_port = self.pipe.bind_to_random_port("inproc://listenerPipe", min_port=12345)
        self.pipeL: zmq.Socket = context.socket(zmq.PAIR)
        self.pipeL.set_hwm(1)
        self.pipeL.connect(f"inproc://listenerPipe:{pipe_port}")

        self.timer = RepeatingTimer(interval=periodic_reading, function=self.queue_readout)
        self.publisher = DataPublisher(full_name=name, log=self.root_logger)

        if auto_connect:
            self.connect(**auto_connect)
        self.log.info(f"Actor '{name}' initialized.")

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.get_parameters)
        self.register_rpc_method(self.set_parameters)
        self.register_rpc_method(self.call_action)
        self.register_rpc_method(self.start_polling)
        self.register_rpc_method(self.stop_polling)
        self.register_rpc_method(self.get_polling_interval)
        self.register_rpc_method(self.set_polling_interval)
        self.register_rpc_method(self.connect)
        self.register_rpc_method(self.disconnect)

    def register_device_method(self, method: Callable) -> None:
        """Make a device method available via RPC. The method name is prefixed with `device.`."""
        # TODO TBD how to call a device method?
        name = method.__name__
        self.register_rpc_method(method=method, name="device." + name)

    def __del__(self) -> None:
        self.disconnect()

    def __exit__(self, *args, **kwargs) -> None:
        super().__exit__(*args, **kwargs)
        self.disconnect()

    def set_full_name(self, full_name: str) -> None:
        super().set_full_name(full_name=full_name)
        self.publisher.full_name = full_name

    def _listen_setup(self) -> zmq.Poller:
        """Setup for listening."""
        poller = super()._listen_setup()
        poller.register(self.pipeL, zmq.POLLIN)
        return poller

    def _listen_loop_element(self, poller: zmq.Poller, waiting_time: Optional[int]
                             ) -> dict[zmq.Socket, int]:
        """Check the socks for incoming messages and handle them.

        :param waiting_time: Timeout of the poller in ms.
        """
        socks = super()._listen_loop_element(poller, waiting_time)
        if self.pipeL in socks:
            self.pipeL.recv()
            self.readout()
            del socks[self.pipeL]
        return socks

    def queue_readout(self) -> None:
        self.pipe.send(b"")

    def read_publish(self, device: Device, publisher: DataPublisher) -> None:
        """Read the device and publish the results.

        Defaults to doing nothing. Implement in a subclass.
        """
        self.log.warning("No 'read_publish' method defined, periodic readout does nothing.")

    def readout(self) -> None:
        """Do periodic readout of the instrument and publish the data.

        Defaults to calling :meth:`read_publish` with the device and publisher as arguments.
        """
        self.read_publish(device=self.device, publisher=self.publisher)

    def start_timer(self, interval: Optional[float] = None) -> None:
        """Start the readout timer.

        :param interval: Readout interval in s. If None, use the last value.
        """
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
        try:
            self.timer.cancel()
        except AttributeError:
            pass

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
        """Connect to the device with the given arguments and keyword arguments."""
        # TODO read auto_connect?
        self.log.info("Connecting")
        self.device = self.device_class(*args, **kwargs)
        self.start_timer()

    def disconnect(self) -> None:
        """Disconnect the device."""
        self.log.info("Disconnecting.")
        self.stop_timer()
        try:
            # Assumes a pymeasure instrument
            self.device.adapter.close()  # type: ignore
        except AttributeError:
            pass
        try:
            del self.device
        except AttributeError:
            pass

    def get_parameters(self, parameters: Union[list[str], tuple[str, ...]]) -> dict[str, Any]:
        """Get device properties from the list `properties`."""
        # `parameters` should be `Iterable[str]`, however, openrpc does not like that.
        data = {}
        for key in parameters:
            path = key.split(".")
            v = self.device
            for attr in path:
                v = getattr(v, attr)
            if callable(v):
                raise TypeError(f"Attribute '{key}' is a callable!")
            data[key] = v
        return data

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        """Set device properties from a dictionary."""
        for key, value in parameters.items():
            path = key.split(".")
            obj = self.device
            for attr in path[:-1]:
                obj = getattr(obj, attr)
            setattr(obj, path[-1], value)

    def call_action(self, action: str, args: Optional[Sequence] = None,
                    kwargs: Optional[dict[str, Any]] = None) -> Any:
        """Call a device action with positional ``args`` and keyword arguments ``kwargs``."""
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        path = action.split(".")
        obj = self.device
        for attr in path[:-1]:
            obj = getattr(obj, attr)
        return getattr(obj, path[-1])(*args, **kwargs)
