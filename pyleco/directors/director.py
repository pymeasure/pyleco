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
from typing import Any, Optional

from ..utils.communicator import CommunicatorProtocol, Communicator
from ..utils.log_levels import get_leco_log_level
from ..core.serialization import generate_conversation_id
from ..core.message import Message


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Director:
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
                 communicator: Optional[CommunicatorProtocol] = None,
                 name: str = "Director",
                 **kwargs) -> None:
        self.actor = actor
        if communicator is None:
            communicator = Communicator(name=name, **kwargs)
            try:
                communicator.sign_in()
            except TimeoutError:
                log.error("Signing in timed out!")
            kwargs = {}
            self._own_communicator = True  # whether to sign out or not.
        else:
            self._own_communicator = False
        self.communicator = communicator
        self.generator = communicator.rpc_generator
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

    # Message handling
    def ask_message(self, actor: Optional[bytes | str] = None,
                    data: Optional[Any] = None) -> Message:
        cid0 = generate_conversation_id()
        actor = self._actor_check(actor)
        log.debug(f"Asking {actor!r} with message '{data}'.")
        response = self.communicator.ask(actor, conversation_id=cid0,
                                         data=data)
        log.debug(f"Data '{response.data}' received.")
        if response.conversation_id == cid0:
            return response
        else:
            raise ValueError(f"Response {response} does not match message_id {cid0!r}.")

    def ask(self, actor: Optional[bytes | str] = None, data: Optional[Any] = None) -> Any:
        """Send a request to the actor and return the content of the response."""
        response = self.ask_message(actor=actor, data=data)
        response_string = response.payload[0]
        return self.generator.get_result_from_response(response_string)

    def _actor_check(self, actor: Optional[str | bytes]) -> str | bytes:
        actor = actor or self.actor
        if actor is None:
            raise ValueError("Some actor has to be specified.")
        return actor

    # Helper methods
    def _prepare_call_action_params(self, args: tuple[Any, ...],
                                    kwargs: dict[str, Any]) -> dict[str, Any]:
        """Generate a params dictionary for the call action method."""
        params = {}
        if args:
            params["args"] = args
        if kwargs:
            params["kwargs"] = kwargs
        return params

    # Remote control synced
    def call_method_rpc(self, method: str, actor: Optional[bytes | str] = None, **kwargs) -> Any:
        string = self.generator.build_request_str(method=method, **kwargs)
        return self.ask(actor=actor, data=string)

    #   Component
    def get_rpc_capabilities(self, actor: Optional[bytes | str] = None) -> dict:
        return self.call_method_rpc(method="rpc.discover", actor=actor)

    def shut_down_actor(self, actor: Optional[bytes | str] = None) -> None:
        """Stop the actor."""
        self.call_method_rpc(method="shut_down", actor=actor)

    def set_actor_log_level(self, level: str | int, actor: Optional[bytes | str] = None
                            ) -> None:
        """Set the log level of the actor"""
        if isinstance(level, int):
            level = get_leco_log_level(level).value
        self.call_method_rpc("set_log_level", level=level, actor=actor)

    #   Actor
    def get_parameters(self, parameters: str | list[str] | tuple[str, ...],
                       actor: Optional[bytes | str] = None) -> dict[str, Any]:
        """Get the values of these `properties` (list, tuple)."""
        if isinstance(parameters, str):
            parameters = (parameters,)
        response = self.call_method_rpc(method="get_parameters", parameters=parameters, actor=actor)
        if not isinstance(response, dict):
            raise ConnectionError("{response} returned, but dict expected.")
        return response

    def set_parameters(self, parameters: dict[str, Any],
                       actor: Optional[bytes | str] = None) -> None:
        """Set the `properties` dictionary."""
        self.call_method_rpc(method="set_parameters", parameters=parameters, actor=actor)

    def call_action(self, action: str, *args, actor: Optional[bytes | str] = None, **kwargs) -> Any:
        """Call an action remotely and return its return value.

        :param str action: Name of the action to call.
        :param \\*args: Arguments for the action to call.
        :param str actor: Name of the actor to execute the action.
            Defaults to the stored actor name.
        :param \\**kwargs: Keyword arguments for the action to call.
        """
        params = self._prepare_call_action_params(args, kwargs)
        return self.call_method_rpc("call_action", action=action, actor=actor, **params)

    # Async methods: Just send, read later.
    def send(self, actor: Optional[bytes | str] = None, data=None) -> bytes:
        """Send a request and return the conversation_id."""
        actor = self._actor_check(actor)
        cid0 = generate_conversation_id()
        self.communicator.send(actor, conversation_id=cid0, data=data)
        return cid0

    def call_method_rpc_async(self, method: str, actor: Optional[bytes | str] = None,
                              **kwargs) -> bytes:
        string = self.generator.build_request_str(method=method, **kwargs)
        return self.send(actor=actor, data=string)

    #   Actor
    def get_parameters_async(self, parameters: list[str] | tuple[str, ...] | str,
                             actor: Optional[bytes | str] = None) -> bytes:
        """Request the values of these `properties` (list, tuple) and return the conversation_id."""
        if isinstance(parameters, str):
            parameters = (parameters,)
        # return self.send(data=[[Commands.GET, properties]])
        return self.call_method_rpc_async(method="get_parameters", parameters=parameters,
                                          actor=actor)

    def set_parameters_async(self, parameters: dict[str, Any],
                             actor: Optional[bytes | str] = None) -> bytes:
        """Set the `properties` dictionary and return the conversation_id."""
        # return self.send(data=[[Commands.SET, properties]])
        return self.call_method_rpc_async(method="set_parameters", parameters=parameters,
                                          actor=actor)

    def call_action_async(self, action: str, *args, actor: Optional[bytes | str] = None,
                          **kwargs) -> bytes:
        """Call a method remotely and return the conversation_id.

        :param str action: Name of the action to call.
        :param \\*args: Arguments for the action to call.
        :param str actor: Name of the actor to execute the action.
            Defaults to the stored actor name.
        :param \\**kwargs: Keyword arguments for the action to call.
        """
        params = self._prepare_call_action_params(args, kwargs)
        return self.call_method_rpc_async(method="call_action", action=action, actor=actor,
                                          **params)
