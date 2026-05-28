#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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
import inspect
import json
import logging
import re
import types
import typing
from typing import Any, Callable, cast, Union
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
    summary: str | None = None
    description: str | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self.method(*args, **kwargs)

    def represent_as_dict(self) -> dict[str, Any]:
        """Describe this method as a dict for discovery."""
        result: dict[str, Any] = {
            "name": self.name,
        }
        if self.summary:
            result["summary"] = self.summary
        if self.description:
            result["description"] = self.description
        params = self._get_params()
        if params:
            result["params"] = params
        result_descriptor = self._get_result()
        if result_descriptor:
            result["result"] = result_descriptor
        return result

    def _get_params(self) -> list[dict[str, Any]]:
        """Introspect method parameters and return Open-RPC param descriptors."""
        try:
            sig = inspect.signature(self.method)
        except (ValueError, TypeError):
            return []
        try:
            hints = typing.get_type_hints(self.method)
        except Exception:
            hints = {}
        globalns = getattr(self.method, "__globals__", None)
        params: list[dict[str, Any]] = []
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            if param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
            ):
                continue
            descriptor: dict[str, Any] = {"name": param_name}
            annotation = hints.get(param_name, param.annotation)
            schema = _python_type_to_schema(annotation, param_name, globalns=globalns)
            if schema:
                descriptor["schema"] = schema
            if param.default is inspect.Parameter.empty:
                descriptor["required"] = True
            else:
                descriptor["required"] = False
                descriptor["schema"] = descriptor.get("schema", {})
                try:
                    json.dumps(param.default)
                    descriptor["schema"]["default"] = param.default
                except (TypeError, ValueError):
                    pass
            params.append(descriptor)
        return params

    def _get_result(self) -> dict[str, Any]:
        """Introspect method return type and return an Open-RPC result descriptor."""
        try:
            hints = typing.get_type_hints(self.method)
        except Exception:
            hints = {}
        if "return" in hints:
            return_annotation = hints["return"]
        else:
            try:
                sig = inspect.signature(self.method)
            except (ValueError, TypeError):
                return {}
            return_annotation = sig.return_annotation
        if return_annotation is inspect.Signature.empty:
            return {}
        globalns = getattr(self.method, "__globals__", None)
        schema = _python_type_to_schema(return_annotation, "result", globalns=globalns)
        if not schema:
            return {}
        return {"name": "result", "schema": schema}


_PEP585_FALLBACKS: dict[str, Any] = {
    "list": typing.List,
    "dict": typing.Dict,
    "set": typing.Set,
    "frozenset": typing.FrozenSet,
    "tuple": typing.Tuple,
    "type": typing.Type,
}
# HACK: remove both _PEP585_FALLBACKS and its usage when Python >= 3.9 is the
# minimum version (PEP 585) and Python >= 3.10 is the minimum version (PEP 604).


def _make_eval_ns(globalns: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build an eval namespace with PEP 585 fallbacks for older Python.

    HACK: remove when Python >= 3.9 is the minimum version.
    """
    ns: dict[str, Any] = {}
    ns.update(_PEP585_FALLBACKS)
    if globalns:
        ns.update(globalns)
    return ns


def _eval_pep604_union(annotation: str, ns: dict[str, Any] | None = None) -> Any:
    """Evaluate a PEP 604 union string (e.g. 'str | None') on Python < 3.10.

    Splits on ``|`` at the top level (outside brackets), evaluates each part
    individually, and returns a ``Union`` of them.

    HACK: remove when Python >= 3.10 is the minimum version.
    """
    namespace = ns or {}
    parts = _split_union(annotation)
    if len(parts) <= 1:
        raise ValueError(f"Not a PEP 604 union: {annotation!r}")
    evaluated = [eval(p.strip(), namespace) for p in parts]
    return Union[tuple(evaluated)]


def _split_union(annotation: str) -> list[str]:
    """Split a type annotation string on ``|`` at the top level only."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(annotation):
        if ch in ("[", "("):
            depth += 1
        elif ch in ("]", ")"):
            depth -= 1
        elif ch == "|" and depth == 0:
            parts.append(annotation[start:i])
            start = i + 1
    parts.append(annotation[start:])
    return parts


def _python_type_to_schema(
    annotation: Any, param_name: str = "", globalns: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema dict for Open-RPC."""
    if annotation is inspect.Parameter.empty or annotation is None:
        return {}
    if isinstance(annotation, str):
        ns = _make_eval_ns(globalns)
        try:
            annotation = eval(annotation, ns)
        except Exception:
            # PEP 604 unions (e.g. "str | None") fail on Python < 3.10 where
            # the | operator on types is not supported.  Parse the string
            # manually and eval each part, then combine via Union.
            # HACK: remove when Python >= 3.10 is the minimum version.
            try:
                annotation = _eval_pep604_union(annotation, ns)
            except Exception:
                return {}
    if annotation is type(None):
        return {"type": "null"}
    type_map: dict[Any, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        bytes: "string",
    }
    if annotation in type_map:
        return {"type": type_map[annotation]}
    origin = typing.get_origin(annotation)
    if origin is not None:
        args = typing.get_args(annotation)
        if origin is Union or origin is getattr(types, "UnionType", None):
            sub_schemas = [s for s in (_python_type_to_schema(a, param_name) for a in args) if s]
            if sub_schemas:
                return {"oneOf": sub_schemas}
            return {}
        if origin is list:
            schema: dict[str, Any] = {"type": "array"}
            if args:
                items = _python_type_to_schema(args[0], param_name)
                if items:
                    schema["items"] = items
            return schema
        if origin is dict:
            schema = {"type": "object"}
            if args and len(args) >= 2:
                val_schema = _python_type_to_schema(args[1], param_name)
                if val_schema:
                    schema["additionalProperties"] = val_schema
            return schema
        return {}
    if isinstance(annotation, type):
        return {"type": "object"}
    return {}


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
        title: str | None = None,
        version: str | None = None,
        debug: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.title = title or "RPC Server"
        self._version = version or "0.1.0"
        self._rpc_methods: dict[str, Method] = {}
        self.method(name="rpc.discover")(self.discover)

    def method(
        self, name: str | None = None, description: str | None = None
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

    def process_request(self, data: bytes | bytearray | str) -> str | None:
        result: JsonRpcResponse | JsonRpcBatch | None
        try:
            json_obj = parse_string(data)
        except JSONRPCError as exc:
            result = self._generate_error(None, error=exc.rpc_error, exc=exc)
        except Exception as exc:
            result = self._generate_error(None, INVALID_REQUEST, exc)
        else:
            result = self.process_request_object(json_obj)
        return result.model_dump_json() if result is not None else None

    def process_request_object(self, json_data: object) -> JsonRpcResponse | JsonRpcBatch | None:
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
        self, obj: JsonRpcRequest | JsonRpcResponse | JsonRpcBatch
    ) -> JsonRpcResponse | JsonRpcBatch | None:
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

    def _process_single_request_object(self, obj: JsonRpcRequest) -> JsonRpcResponse | None:
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

    def _get_method(self, method_name: str) -> Method | None:
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
        self, id_: int | str | None, method_name: str
    ) -> JsonRpcResponse | None:
        """Handle method not found error."""
        error = METHOD_NOT_FOUND.with_data(data=method_name)
        return self._generate_error(
            id=id_,
            error=error,
            exc=None,
            return_response=id_ is not None,
        )

    def _handle_type_error(
        self, id_: int | str | None, obj: JsonRpcRequest, exc: TypeError
    ) -> JsonRpcResponse | None:
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
        self, id_: int | str | None, exc: Exception
    ) -> JsonRpcResponse | None:
        """Handle general exceptions during method execution."""
        error = INTERNAL_ERROR.with_data(data=f"{type(exc).__name__}: {exc}")
        return self._generate_error(
            id_,
            error,
            exc=exc,
            return_response=id_ is not None,
        )

    @staticmethod
    def _generate_invalid_request_error(reason: str, data: Any) -> JsonRpcError:
        return INVALID_REQUEST.with_data(data={"reason": reason, "data": data})

    @staticmethod
    def _generate_error(
        id: int | str | None,
        error: JsonRpcError,
        exc: Exception | None,
        return_response: bool = True,
    ) -> JsonRpcResponse | None:
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
