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

"""
These classes show which methods have to be available via RPC in order to comply with LECO message
definitions.

A combination of type checking and unit tests can test the compliance with LECO definitions.

For example, if you want to verify, that the class `Actor` fulfills the requirements for a
Component, for an Actor which supports Polling and setting the log level, you may use the following
tests.

For a static test, that all the methods are present with the correct types, the following works:

.. code::

    class ExtendedActorProtocol(ExtendedComponentProtocol, PollingActorProtocol, Protocol):
        "Combine all required Protocols for the class under test."
        pass

    def static_test_methods_are_present():
        def testing(component: ExtendedActorProtocol):
            pass
        testing(Actor(name="test", cls=FantasyInstrument))

For unit test, that all the necessary methods are reachable via RPC, the following works:

.. code::

    protocol_methods = [m for m in dir(ExtendedActorProtocol) if not m.startswith("_")]

    @pytest.fixture
    def component_methods(actor: Actor):
        response = actor.rpc.process_request(
            '{"id": 1, "method": "rpc.discover", "jsonrpc": "2.0"}')
        result = actor.rpc_generator.get_result_from_response(response)  # type: ignore
        return result.get('methods')

    @pytest.mark.parametrize("method", protocol_methods)
    def test_method_is_available(component_methods, method):
        for m in component_methods:
            if m.get('name') == method:
                return
        raise AssertionError(f"Method {method} is not available.")
"""

from __future__ import annotations
try:
    from enum import StrEnum  # type: ignore
except ImportError:
    # For python<3.11
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore
        pass

from typing import Any, Iterable, Optional, Protocol, Sequence


class ComponentProtocol(Protocol):
    """Any Component of the LECO protocol."""

    def pong(self) -> None:
        """Respond to any request."""
        return  # always succeeds.


class LogLevels(StrEnum):
    """Log levels for :meth:`ExtendedComponentProtocol.set_log_level` method."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ExtendedComponentProtocol(ComponentProtocol, Protocol):
    """A Component which supports more features."""

    def set_log_level(self, level: LogLevels) -> None: ...

    def shut_down(self) -> None: ...


class CoordinatorProtocol(ComponentProtocol, Protocol):
    """A command protocol Coordinator."""

    def sign_in(self) -> None: ...

    def sign_out(self) -> None: ...

    def coordinator_sign_in(self) -> None: ...

    def coordinator_sign_out(self) -> None: ...

    def add_nodes(self, nodes: dict[str, str]) -> None: ...

    def send_nodes(self) -> dict[str, str]: ...

    def record_components(self, components: list[str]) -> None: ...

    def send_local_components(self) -> list[str]: ...

    def send_global_components(self) -> dict[str, list[str]]: ...

    def remove_expired_addresses(self, expiration_time: float) -> None: ...


class ActorProtocol(ComponentProtocol, Protocol):
    """An Actor Component."""

    def get_parameters(self, parameters: Iterable[str]) -> dict[str, Any]: ...

    def set_parameters(self, parameters: dict[str, Any]) -> None: ...

    def call_action(self, action: str, args: Optional[Sequence[Any]] = None,
                    kwargs: Optional[dict[str, Any]] = None) -> Any: ...


class PollingActorProtocol(ActorProtocol, Protocol):
    """An Actor which allows regular polling."""

    def start_polling(self, polling_interval: Optional[float]) -> None: ...

    def set_polling_interval(self, polling_interval: float) -> None: ...

    def get_polling_interval(self) -> float: ...

    def stop_polling(self) -> None: ...


class LockingActorProtocol(ActorProtocol, Protocol):
    """An Actor which allows to lock the device or channels of the device."""

    def lock(self, resource: Optional[str] = None) -> bool: ...

    def unlock(self, resource: Optional[str] = None) -> None: ...

    def force_unlock(self, resource: Optional[str] = None) -> None: ...
