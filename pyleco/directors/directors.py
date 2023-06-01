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
from typing import List, Optional

from pytrinamic.modules import TMCM6110

from ..utils.communicator import Communicator, SimpleCommunicator
from ..core.enums import Commands, Errors, StrEnum
from ..core.serialization import generate_conversation_id


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class BaseDirector:
    """Basic director handling.

    They can be used as a ContextManager:
    .. code::

        with BaseDirector() as d:
            d.get_properties(["property1", "property2"])

    :param actor: Default name of the Actor to cummunicate with. Stored as :attr:`actor`.
    :param communicator: A Communicator class to communicate with the actor.
        If None, create a new Communicator instance.
    :param name: The name of this Director.
    """

    def __init__(self, actor: Optional[bytes | str] = None,
                 communicator: Optional[Communicator] = None,
                 name: str = "Director",
                 **kwargs) -> None:
        self.actor = actor
        if communicator is None:
            communicator = SimpleCommunicator(name=name, **kwargs)
            try:
                communicator.sign_in()
            except TimeoutError:
                log.error("Signing in timed out!")
            kwargs = {}
            self._own_communicator = True  # whether to sign out or not.
        else:
            self._own_communicator = False
        self.communicator = communicator
        super().__init__(**kwargs)

    def close(self) -> None:
        if self._own_communicator:
            self.communicator.close()

    def sign_out(self) -> None:
        """Sign the communicator out."""
        self.communicator.sign_out()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    # Remote control
    def ask(self, actor: Optional[bytes | str] = None, data: object = None) -> object:
        """Send a request to the actor and return the content of the response."""
        cid0 = generate_conversation_id()
        actor = self._actor_check(actor)
        response = self.communicator.ask(actor, conversation_id=cid0,
                                         data=data)
        log.debug(f"Data {response.data} received.")
        if response.conversation_id == cid0:
            command = response.data[0]  # First message
            if command[0] == Commands.ACKNOWLEDGE:
                return command[-1]  # content is second value, if any.
            elif command[0] == Commands.ERROR:
                if command[1] == Errors.NAME_NOT_FOUND and len(command) == 3:
                    raise AttributeError(command[2])
                elif command[1] == Errors.EXECUTION_FAILED and len(command) == 4:
                    # TODO get the original Exception type
                    raise ValueError(f"{command[2]}: {command[3]}")
                else:
                    raise ValueError(f"An error occurred: {response.data[0][1:]}")
        else:
            raise ValueError(f"Response {response} does not match message_id {cid0}.")

    def _actor_check(self, actor: Optional[str | bytes]) -> str | bytes:
        actor = actor or self.actor
        if actor is None:
            raise ValueError("Some actor has to be specified.")
        return actor

    def get_properties(self, properties: str | list | tuple) -> dict:
        """Get the values of these `properties` (list, tuple)."""
        if isinstance(properties, str):
            properties = (properties,)
        response = self.ask(data=[[Commands.GET, properties]])
        if not isinstance(response, dict):
            raise ConnectionError("{response} returned, but dict expected.")
        return response

    def set_properties(self, properties: dict) -> None:
        """Set the `properties` dictionary."""
        self.ask(data=[[Commands.SET, properties]])

    def call_method(self, method: str, *args, **kwargs) -> object:
        """Call a method remotely and return its return value.

        :param str method: Name of the method to call.
        :param \\*args: Arguments for the method to call.
        :param \\**kwargs: Keyword arguments for the method to call.
        """
        kwargs.setdefault('_name', method)
        if args:
            kwargs.setdefault("_args", args)
        return self.ask(data=[[Commands.CALL, kwargs]])

    def stop_actor(self) -> None:
        """Stop the actor."""
        self.ask(data=[[Commands.OFF]])

    #   Async methods: Just send, read later.
    def send(self, actor: Optional[bytes | str] = None, data=None) -> bytes:
        """Send a request and return the conversation_id."""
        actor = self._actor_check(actor)
        cid0 = generate_conversation_id()
        self.communicator.send(actor, conversation_id=cid0, data=data)
        return cid0

    def get_properties_async(self, properties: list | tuple | str) -> bytes:
        """Request the values of these `properties` (list, tuple) and return the conversation_id."""
        if isinstance(properties, str):
            properties = (properties,)
        return self.send(data=[[Commands.GET, properties]])

    def set_properties_async(self, properties: dict) -> bytes:
        """Set the `properties` dictionary and return the conversation_id."""
        return self.send(data=[[Commands.SET, properties]])

    def call_method_async(self, method: str, *args, **kwargs) -> bytes:
        """Call a method remotely and return the conversation_id.

        :param str method: Name of the method to call.
        :param \\*args: Arguments for the method to call.
        :param \\**kwargs: Keyword arguments for the method to call.
        """
        kwargs.setdefault('_name', method)
        if args:
            kwargs.setdefault("_args", args)
        return self.send(data=[[Commands.CALL, kwargs]])


class RemoteCall:
    """Descriptor for remotely calling methods.

    You can add methods by simpling adding this Descriptor.
    Whenever this instance is called, it executes :code:`call_method`
    with the attribute name as `method` parameter. For example:

    .. code::

        class XYZ(BaseDirector):
            method = RemoteCall("Docstring for that method.")  # add a RemoteCall instance as attr.
        director = XYZ()
        director.method(*some_args, **kwargs)  # execute this instance.
        # equivalent to:
        director.call_method("method", *some_args, **kwargs)

    :param str doc: Docstring for the method. {name} is replaced by the attribute name of the
        instance of RemoteCall, in the example by 'method'.
    """

    def __init__(self, doc: str = "Call '{name}' at the remote driver.", **kwargs) -> None:
        self._doc = doc
        super().__init__(**kwargs)

    def __set_name__(self, owner, name) -> None:
        self._name = name
        self._doc = self._doc.format(name=self._name)

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self

        def remote_call(*args, **kwargs):
            obj.call_method(self._name, *args, **kwargs)

        remote_call.__doc__ = self._doc
        return remote_call


class TransparentDirector(BaseDirector):
    """Director getting/setting all properties remotely.

    Whenever you try to get/set a property, which does not belong to the director itself,
    it tries to get/set it remotely from the actor.
    If you want to add method calls, you might use the :class:`RemoteCall` Descriptor to add methods
    to a subclass. For example :code:`method = RemoteCall()` in the class definition will make sure,
    that :code:`method(*args, **kwargs)` will be executed remotely.
    """

    def __getattr__(self, name):
        if name in dir(self):
            return super().__getattribute__(name)
        else:
            return self.get_properties((name,)).get(name)

    def __setattr__(self, name, value) -> None:
        if name in dir(self) or name.startswith("_") or name in ("actor", "communicator"):
            super().__setattr__(name, value)
        else:
            self.set_properties({name: value})

    # TODO generate a list of capabilities of the actor and return these capabilites during a call
    # to __dir__. That enables autocompletion etc.


class CoordinatorDirector(BaseDirector):
    """Direct a Coordinator."""

    def __init__(self, actor="COORDINATOR", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def get_directory(self) -> object:
        """Get the directory."""
        return self.ask(data=[[Commands.GET, ['directory', 'nodes']]])

    def get_global_directory(self) -> object:
        """Get the directory."""
        return self.ask(data=[[Commands.LIST]])

    def set_directory(self, coordinators: dict) -> object:
        """Tell the Coordinator about other coordinators (dict)."""
        return self.ask(data=[[Commands.SET, {'nodes': coordinators}]])


class MotorDirector(BaseDirector):
    """Direct a stepper motor card.

    :param str actor: Name of the card actor.
    :param int motor_count: Number of motor connections.
    """

    def __init__(self, actor, motor_count=6, **kwargs) -> None:
        self.motors = [self.Motor(parent=self, number=i) for i in range(motor_count)]
        super().__init__(actor=actor, **kwargs)

    class Motor:
        """Simulating a real motor as a drop in replacement for a motor card."""

        def __init__(self, parent, number: int) -> None:
            self.parent = parent
            self.number = number

        AP = TMCM6110._MotorTypeA.AP

        def get_axis_parameter(self, ap_type, signed=False):
            return self.parent.get_axis_parameter(ap_type, self.number, signed)

        def set_axis_parameter(self, ap_type, value) -> None:
            self.parent.set_axis_parameter(ap_type, self.number, value)

        @property
        def actual_position(self) -> int:
            return self.parent.get_actual_position(self.number)

        @actual_position.setter
        def actual_position(self, steps) -> None:
            self.parent.set_actual_position(self.number, steps)

        @property
        def actual_velocity(self) -> int:
            return self.parent.get_actual_velocity(self.number)

        def rotate(self, velocity) -> None:
            self.parent.rotate(self.number, velocity)

        def stop(self) -> None:
            self.parent.stop(self.number)

        def move_by(self, difference: int, velocity=None) -> None:
            self.parent.move_by(self.number, difference, velocity)

        def move_to(self, position: int, velocity=None) -> None:
            self.parent.move_to(self.number, position, velocity)

        def get_position_reached(self) -> bool:
            return self.parent.get_position_reached(self.number)

    # General methods
    def disconnect(self) -> None:
        """Disconnect the card."""
        self.call_method("disconnect")

    def configure_motor(self, config: dict):
        """Configure a motor according to the dictionary."""
        return self.call_method("configure_motor", config)

    def get_configuration(self, motor):
        """Get the configuration of `motor`."""
        return self.call_method("get_configuration", motor)

    def get_global_parameter(self, gp_type, bank, signed=False):
        return self.call_method("get_global_parameter", gp_type, bank, signed)

    def set_global_parameter(self, gp_type, bank, value):
        return self.call_method("set_global_parameter", gp_type, bank, value)

    def get_axis_parameter(self, ap_type, axis, signed=False):
        return self.call_method("get_axis_parameter", ap_type, axis, signed)

    def set_axis_parameter(self, ap_type, axis, value):
        return self.call_method("set_axis_parameter", ap_type, axis, value)

    # Motor controls
    def stop(self, motor):
        """Stop a motor."""
        return self.call_method("stop", motor)

    def get_actual_velocity(self, motor):
        """Get the current velocity of the motor."""
        return self.call_method("get_actual_velocity", motor)

    def get_actual_position(self, motor):
        """Get the current position of the motor."""
        return self.call_method("get_actual_position", motor)

    def get_actual_units(self, motor):
        """Get the actual position in units."""
        return self.call_method("get_actual_units", motor)

    def set_actual_position(self, motor, steps):
        """Set the current position in steps."""
        return self.call_method("set_actual_position", motor, steps)

    def move_to(self, motor, position, velocity=None):
        """Move to a specific position."""
        if velocity is None:
            args = (motor, position)
        else:
            args = (motor, position, velocity)
        return self.call_method("move_to", *args)

    def move_to_units(self, motor, position, velocity=None):
        """Move to a specific position in units."""
        if velocity is None:
            args = (motor, position)
        else:
            args = (motor, position, velocity)
        return self.call_method("move_to_units", *args)

    def move_by(self, motor, difference, velocity=None):
        """Move to a specific position."""
        if velocity is None:
            args = (motor, difference)
        else:
            args = (motor, difference, velocity)
        return self.call_method("move_by", *args)

    def move_by_units(self, motor, difference, velocity=None):
        """Move to a specific position."""
        if velocity is None:
            args = (motor, difference)
        else:
            args = (motor, difference, velocity)
        return self.call_method("move_by_units", *args)

    def rotate(self, motor, velocity):
        """Rotate the motor with a specific velocity."""
        return self.call_method("rotate", motor, velocity)

    def get_position_reached(self, motor):
        """Get whether the motor reached its position."""
        return self.call_method("get_position_reached", motor)

    def get_motor_dict(self):
        """Get the motor name dictionary."""
        return self.call_method("get_motor_dict")

    def set_motor_dict(self, motor_dict):
        """Set a motor name dictionary (dict type)."""
        return self.call_method("set_motor_dict", motor_dict)

    # In/outs
    def get_analog_input(self, connection):
        """Return the analog input value of input `connection`."""
        return self.call_method("get_analog_input", connection)

    def get_digital_input(self, connection):
        """Return the digital input value of input `connection`."""
        return self.call_method("get_digital_input", connection)

    def get_digital_output(self, connection):
        """Return the state of the digital output with number `connection`."""
        return self.call_method("get_digital_output", connection)

    def set_digital_output(self, connection, enabled):
        """Set the digital output at `connection` to bool `enabled`."""
        return self.call_method("set_digital_output", connection, enabled)


class StarterCommands(StrEnum):
    """Commands for the starter."""

    LIST = "T"
    START = "S"
    STOP = "X"
    RESTART = "R"
    STATUS = "?"
    INSTALL = "I"


class StarterDirector(BaseDirector):
    """Director for the Starter.

    :param actor: Name of the actor to direct.
    """

    def __init__(self, actor: str = "starter", **kwargs) -> None:
        super().__init__(actor=actor, **kwargs)

    def send_json(self, name: Optional[bytes | str] = None, data=None, **kwargs) -> None:
        """Send a message without returning an answer."""
        actor = self._actor_check(actor=name)
        self.communicator.send(actor, data=data, **kwargs)

    def ask_json(self, name: Optional[bytes | str] = None, data=None, **kwargs) -> List[list]:
        """Send a message and read the answer, returning the content."""
        kwargs.setdefault("conversation_id", generate_conversation_id())
        actor = self._actor_check(actor=name)
        response = self.communicator.ask(actor, data=data, **kwargs)
        if response.conversation_id == kwargs["conversation_id"]:
            return response.data
        else:
            raise ConnectionError(
                "Wrong message received.",
                f"{response.data} from {response.sender} with id {response.conversation_id}", )

    def start_tasks(self, names: List[str] | str, name: Optional[bytes | str] = None) -> None:
        """Start the task or tasks.

        :param names: Single task name or list of task names to start.
        :param name: Name of the starter to communicate with.
        """
        self.send_json(name, data=[(StarterCommands.START, names)])

    def restart_tasks(self, names: List[str] | str, name: Optional[bytes | str] = None) -> None:
        """Restart the task or tasks.

        :param names: Single task name or list of task names to restart.
        :param name: Name of the starter to communicate with.
        """
        self.send_json(name, data=[(StarterCommands.RESTART, names)])

    def stop_tasks(self, names: List[str] | str, name: Optional[bytes | str] = None) -> None:
        """Stop the task or tasks.

        :param names: Single task name or list of task names to stop.
        :param name: Name of the starter to communicate with.
        """
        self.send_json(name, data=[(StarterCommands.STOP, names)])

    def install_tasks(self, names: List[str] | str, name: Optional[bytes | str] = None) -> None:
        """Install the tasks.

        :param names: Single task name or list of task names to install.
        :param name: Name of the starter to communicate with.
        """
        self.send_json(name, data=[(StarterCommands.INSTALL, names)])

    def status_tasks(self, names: Optional[List[str] | str] = None,
                     name: Optional[bytes | str] = None):
        """Query the status of these tasks and all running ones.

        :param names: List of task names to ask for.
        :param name: Name of the starter to communicate with.
        """
        data = self.ask_json(name, data=[(StarterCommands.STATUS, names)])
        assert data[0][0] == StarterCommands.STATUS, (
            f"Returned command '{data[0][0]}' is not '{StarterCommands.STATUS}' status command.")
        return data[0][1]

    def shutdown(self, confirmation: bool = False, name: Optional[bytes | str] = None) -> None:
        """Shut the starter down, confirmation is required."""
        if confirmation:
            self.send_json(name, data=[[Commands.OFF]])

    def list_tasks(self, name: Optional[bytes | str] = None):
        """List all available tasks with name and tooltip."""
        data = self.ask_json(name, data=[[StarterCommands.LIST]])
        assert data[0][0] == StarterCommands.LIST, (
            f"Returned command '{data[0][0]}' is not '{StarterCommands.LIST}' list command.")
        return data[0][1]
