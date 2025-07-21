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
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, Union

from ..core.message import Message, MessageTypes
from ..json_utils.rpc_generator import RPCGenerator
from ..json_utils.rpc_server import RPCServer


ReturnValue = TypeVar("ReturnValue")


class RpcHandler:
    """Handles registration and processing of RPC methods in LECO context."""

    current_message: Message
    additional_response_payload: Optional[list[bytes]]

    def __init__(self, title: str = "RpcHandler") -> None:
        self.rpc = RPCServer(title=title)
        self.rpc_generator = RPCGenerator()

    def register_rpc_method(self, method: Callable[..., Any], **kwargs) -> None:
        """Register a method to be available via rpc calls."""
        self.rpc.method(**kwargs)(method)

    def _handle_binary_return_value(
        self, return_value: tuple[ReturnValue, list[bytes]]
    ) -> ReturnValue:
        self.additional_response_payload = return_value[1]
        return return_value[0]

    @staticmethod
    def _pass_through(return_value: ReturnValue) -> ReturnValue:
        return return_value

    def _generate_binary_capable_method(
        self,
        method: Callable[..., Union[ReturnValue, tuple[ReturnValue, list[bytes]]]],
        accept_binary_input: bool = False,
        return_binary_output: bool = False,
    ) -> Callable[..., ReturnValue]:
        returner = self._handle_binary_return_value if return_binary_output else self._pass_through

        if accept_binary_input:

            @wraps(method)
            def modified_method(*args, **kwargs) -> ReturnValue:  # type: ignore
                if args:
                    args_l = list(args)
                    if args_l[-1] is None:
                        args_l[-1] = self.current_message.payload[1:]
                    else:
                        args_l.append(self.current_message.payload[1:])
                    args = args_l  # type: ignore[assignment]
                else:
                    kwargs["additional_payload"] = self.current_message.payload[1:]
                return_value = method(
                    *args, **kwargs
                )
                return returner(return_value=return_value)  # type: ignore
        else:

            @wraps(method)
            def modified_method(*args, **kwargs) -> ReturnValue:
                return_value = method(*args, **kwargs)
                return returner(return_value=return_value)  # type: ignore

        doc_addition = (
            f"(binary{' input' * accept_binary_input}{' output' * return_binary_output} method)"
        )
        try:
            modified_method.__doc__ += "\n" + doc_addition  # type: ignore[operator]
        except TypeError:
            modified_method.__doc__ = doc_addition
        return modified_method  # type: ignore

    def register_binary_rpc_method(
        self,
        method: Callable[..., Union[Any, tuple[Any, list[bytes]]]],
        accept_binary_input: bool = False,
        return_binary_output: bool = False,
        **kwargs,
    ) -> None:
        """Register a method which accepts binary input and/or returns binary values.

        :param accept_binary_input: the method must accept the additional payload as an
            `additional_payload=None` parameter (default value must be present as `None`!).
        :param return_binary_output: the method must return a tuple of a JSON-able python object
            (e.g. `None`) and of a list of bytes objects, to be sent as additional payload.
        """
        modified_method = self._generate_binary_capable_method(
            method=method,
            accept_binary_input=accept_binary_input,
            return_binary_output=return_binary_output,
        )
        self.register_rpc_method(modified_method, **kwargs)

    def process_request(self, message: Message) -> Optional[Message]:
        """Process an RPC request and return the response message."""
        if message.payload is None:
            return None

        self.current_message = message
        self.additional_response_payload = None

        reply = self.rpc.process_request(message.payload[0])
        if reply is None:
            return None

        return Message(
            message.sender,
            conversation_id=message.conversation_id,
            message_type=MessageTypes.JSON,
            data=reply,
            additional_payload=self.additional_response_payload,
        )
