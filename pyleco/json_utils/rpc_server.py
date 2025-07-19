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
import logging
import re
from typing import Any, Callable, cast, Optional, Union
from dataclasses import dataclass

from .errors import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    InvalidRequest,
    JSONRPCError,
)
from .json_objects import (
    ResultResponse,
    ErrorResponse,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcBatch,
    JsonRpcError,
)
from .json_parser import get_json_object, parse_string


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@dataclass
class Method:
    """Describe a method with its attributes."""

    # See https://spec.open-rpc.org/#method-object for values
    method: Callable
    name: str
    # params  # TODO
    summary: Optional[str] = None
    description: Optional[str] = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.method(*args, **kwargs)

    def represent_as_dict(self) -> dict:
        """Describe this method as a dict for discovery."""
        result = {
            "name": self.name,
        }
        if self.summary:
            result["summary"] = self.summary
        if self.description:
            result["description"] = self.description
        return result


class RPCServer:
    """A simple JSON-RPC server.

    Security Considerations:
    - Method names are restricted to alphanumeric characters, underscores and periods
    - Payload size limits should be enforced at the transport layer
    - Untrusted input should be carefully validated in method implementations

    If you register a method with the `method` decorator, it will be available
    for remote calls.
    The `process_request` method is used to process a JSON-RPC request and return
    the result as a JSON string.

    .. code-block:: python
        rpc = RPCServer()
        @rpc.method
        def add(a, b):
            return a + b

        result = rpc.process_request('{"method": "add", "params": [1, 2], "id": 1}')
        print(result)  # '{"jsonrpc": "2.0", "result": 3, "id": 1}'

    It is similar to the RPCServer provided by the `openrpc` package, which it replaces.
    """

    def __init__(
        self,
        title: Optional[str] = None,
        version: Optional[str] = None,
        debug: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.title = title or "RPC Server"
        self._version = version or "0.1.0"
        self._rpc_methods: dict[str, Method] = {}
        self.method(name="rpc.discover")(self.discover)

    def method(
        self, name: Optional[str] = None, description=None, **kwargs
    ) -> Callable[[Callable], None]:
        """Decorator for registering a new RPC method.

        Method names must be valid identifiers (alphanumeric + underscores + periods).
        """

        def method_registrar(method: Callable) -> None:
            store_name = name or method.__name__
            # Validate method name format
            if store_name in self._rpc_methods.keys():
                raise ValueError(f"Method name '{store_name}' already defined.")
            if not re.fullmatch(r"[\w\.]+", store_name):
                raise ValueError(
                    f"Invalid method name: {store_name!r}."
                    " Only alphanumeric, underscore and period characters are allowed."
                )
            store_description = description
            method_dict = {}
            if method.__doc__:
                lines = method.__doc__.split("\n")
                method_dict["summary"] = lines[0]
                if not store_description and lines[1:]:
                    store_description = " ".join(line.strip() for line in lines[1:] if line).strip()
            method_container = Method(
                method=method, name=store_name, description=store_description, **method_dict
            )
            self._rpc_methods[store_name] = method_container
            return None

        return method_registrar

    def unregister_method(self, name: str) -> None:
        self._rpc_methods.pop(name, None)

    def process_request(self, data: Union[bytes, str]) -> Optional[str]:
        result: Optional[Union[JsonRpcResponse, JsonRpcBatch]]
        try:
            json_obj = parse_string(data)
        except JSONRPCError as exc:
            result = self._generate_error(None, error=exc.rpc_error, exc=exc)
        except Exception as exc:
            result = self._generate_error(None, INVALID_REQUEST, exc)
        else:
            result = self.process_request_object(json_obj)
        return result.model_dump_json() if result is not None else None

    def process_request_object(
        self, json_data: object
    ) -> Optional[Union[JsonRpcResponse, JsonRpcBatch]]:
        """Process a JSON-RPC request executing the associated method."""
        try:
            obj = get_json_object(json_data)
        except InvalidRequest as exc:
            return ErrorResponse(id=None, error=exc.rpc_error)
        try:
            return self.process_json_request_object(obj)
        except Exception as exc:
            return self._generate_error(None, INTERNAL_ERROR, exc)

    def process_json_request_object(
        self, obj: Union[JsonRpcRequest, JsonRpcResponse, JsonRpcBatch]
    ) -> Optional[Union[JsonRpcResponse, JsonRpcBatch]]:
        if isinstance(obj, JsonRpcBatch) and obj.is_request_batch:
            result = [
                response
                for element in obj.items
                if (response := self._process_single_request_object(cast(JsonRpcRequest, element)))
                is not None
            ]
            return JsonRpcBatch(result) if result else None
        elif isinstance(obj, (JsonRpcRequest)):
            return self._process_single_request_object(obj)
        else:
            return ErrorResponse(
                id=None,
                error=self._generate_invalid_request_error("Not a request", obj.model_dump()),
            )

    def _process_single_request_object(self, obj: JsonRpcRequest) -> Optional[JsonRpcResponse]:
        id_ = obj.id
        method = self._get_method(obj.method)

        if not method:
            return self._handle_method_not_found(id_, obj.method)

        try:
            result = self._execute_method(method, obj)
        except JSONRPCError as exc:
            return self._generate_error(id_, exc.rpc_error, exc)
        except TypeError as exc:
            return self._handle_type_error(id_, obj, exc)
        except Exception as exc:
            return self._handle_general_error(id_, exc)

        return ResultResponse(id=id_, result=result) if id_ is not None else None

    def _get_method(self, method_name: str) -> Optional[Method]:
        return self._rpc_methods.get(method_name)

    def _execute_method(self, method: Method, obj: JsonRpcRequest) -> Any:
        """Execute the method with appropriate parameters based on request type."""
        if obj.params is None:
            return method()
        elif isinstance(obj.params, list):
            return method(*obj.params)
        elif isinstance(obj.params, dict):
            return method(**obj.params)
        raise InvalidRequest(
            self._generate_invalid_request_error(
                "Parameters are neither list nor dict", obj.model_dump()
            )
        )

    def _handle_method_not_found(
        self, id_: Optional[Union[int, str]], method_name: str
    ) -> Optional[JsonRpcResponse]:
        """Handle method not found error."""
        error = METHOD_NOT_FOUND.with_data(data=method_name)
        return self._generate_error(
            id=id_,
            error=error,
            exc=None,
            return_response=id_ is not None,
        )

    def _handle_type_error(
        self, id_: Optional[Union[int, str]], obj: JsonRpcRequest, exc: TypeError
    ) -> Optional[JsonRpcResponse]:
        """Handle TypeError during method execution."""
        if isinstance(obj.method, str) and str(exc).startswith(f"{obj.method}()"):
            # The method complains about invalid arguments
            error = INVALID_PARAMS.with_data(data=obj.model_dump())
        else:
            error = INTERNAL_ERROR.with_data(data=f"{type(exc).__name__}: {exc}")

        return self._generate_error(
            id_,
            error,
            exc=exc,
            return_response=id_ is not None,
        )

    def _handle_general_error(
        self, id_: Optional[Union[int, str]], exc: Exception
    ) -> Optional[JsonRpcResponse]:
        """Handle general exceptions during method execution."""
        error = INTERNAL_ERROR.with_data(data=f"{type(exc).__name__}: {exc}")
        return self._generate_error(
            id_,
            error,
            exc=exc,
            return_response=id_ is not None,
        )

    @staticmethod
    def _generate_invalid_request_error(reason: str, data: Any):
        return INVALID_REQUEST.with_data(data={"reason": reason, "data": data})

    @staticmethod
    def _generate_error(
        id: Optional[Union[int, str]],
        error: JsonRpcError,
        exc: Optional[Exception],
        return_response: bool = True,
    ) -> Optional[JsonRpcResponse]:
        if exc is None:
            log.error(
                f"Error during message handling: '{error.message}': %s.", error.model_dump_json()
            )
        else:
            log.exception(f"{type(exc).__name__} causes '{error.message}'.", exc_info=exc)
        return ErrorResponse(id, error=error) if return_response else None

    def discover(self) -> dict[str, Any]:
        """List all the capabilities of the server."""
        result: dict[str, Any] = {"openrpc": "1.2.6"}
        result["info"] = {"title": self.title, "version": self._version}
        methods: list[dict[str, Any]] = []
        for method in self._rpc_methods.values():
            if method.name == "rpc.discover":
                # do not list it
                continue
            methods.append(method.represent_as_dict())
        result["methods"] = methods
        return result
