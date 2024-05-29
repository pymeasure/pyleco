#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
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
from typing import Any, Generic, Optional, Sequence, TypeVar, Union

from zmq import Context

from ..core.message import Message
from .actor import Actor


Device = TypeVar("Device")


class AccessError(BaseException):
    # TODO name TBD
    pass


class LockingActor(Actor, Generic[Device]):
    """An Actor which allows to lock the device or parts of it."""

    current_message: Message

    def __init__(
        self,
        name: str,
        device_class: Optional[type[Device]] = None,
        periodic_reading: float = -1,
        auto_connect: Optional[dict] = None,
        context: Optional[Context] = None,
        **kwargs,
    ):
        super().__init__(name, device_class, periodic_reading, auto_connect, context, **kwargs)
        self._locks: dict[Optional[str], bytes] = {}

    def register_rpc_methods(self) -> None:
        super().register_rpc_methods()
        self.register_rpc_method(self.lock)
        self.register_rpc_method(self.unlock)
        self.register_rpc_method(self.force_unlock)

    # RPC methods for locking
    def lock(self, resource: Optional[str] = None) -> bool:
        """Lock the controlled device or one of its resources and return the success state."""
        current_owner = self._locks.get(resource)
        if current_owner is None:
            self._locks[resource] = self.current_message.sender
            return True
        elif current_owner == self.current_message.sender:
            return True
        else:
            return False

    def unlock(self, resource: Optional[str] = None) -> None:
        """Unlock the controlled device or one of its resources.

        Only the locking Component may unlock.
        """
        current_owner = self._locks.get(resource)
        if current_owner is None:
            self._locks[resource] = self.current_message.sender
            return  # True
        elif current_owner == self.current_message.sender:
            self._locks.pop(resource, None)
            return  # True
        else:
            return  # False

    def force_unlock(self, resource: Optional[str] = None) -> None:
        """Unlock the controlled device or one of its resources even if someone else locked it."""
        self._locks.pop(resource, None)

    # modified methods for device access
    def process_json_message(self, message: Message) -> Message:
        self.current_message = message
        return super().process_json_message(message=message)

    def get_parameters(self, parameters: Union[list[str], tuple[str, ...]]) -> dict[str, Any]:
        # `parameters` should be `Iterable[str]`, however, openrpc does not like that.
        for parameter in parameters:
            self._check_access_rights_raising(parameter)
        return super().get_parameters(parameters=parameters)

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        for parameter in parameters.keys():
            self._check_access_rights_raising(parameter)
        return super().set_parameters(parameters=parameters)

    def call_action(
        self, action: str, args: Optional[Sequence] = None, kwargs: Optional[dict[str, Any]] = None
    ) -> Any:
        self._check_access_rights_raising(action)
        return super().call_action(action=action, args=args, kwargs=kwargs)

    # helper methods
    def _check_access_rights(self, resource: Optional[str]) -> bool:
        requester = self.current_message.sender
        if resource is None:
            elements = []
        else:
            elements = resource.split(".")
        for i in range(-1, len(elements)):
            local_owner = self._locks.get(".".join(elements[:i + 1])) if i >= 0 else None
            if local_owner is not None and requester != local_owner:
                return False
        return True

    def _check_access_rights_raising(self, resource: str) -> None:
        if self._check_access_rights(resource=resource) is False:
            raise AccessError
