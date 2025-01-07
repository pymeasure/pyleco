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
import json
import logging
from typing import Any, Callable, Optional, Union

from .errors import INTERNAL_ERROR, SERVER_ERROR, INVALID_REQUEST
from .json_objects import ResultResponse, ErrorResponse, DataError, ResponseType, ResponseBatch


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class RPCServer:
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
        self._rpc_methods: dict[str, Callable] = {}
        self.method(name="rpc.discover")(self.discover)

    def method(self, name: Optional[str] = None, **kwargs) -> Callable[[Callable], None]:
        def method_registrar(method: Callable) -> None:
            return self._register_method(name=name or method.__name__, method=method)
        return method_registrar

    def _register_method(self, name: str, method: Callable) -> None:
        self._rpc_methods[name] = method

    def process_request(self, data: Union[bytes, str]) -> Optional[str]:
        try:
            json_data = json.loads(data)
            result = self.process_request_object(json_data=json_data)
            return result.model_dump_json() if result else None
        except Exception as exc:
            log.exception(f"{type(exc).__name__}:", exc_info=exc)
            return ErrorResponse(id=None, error=INTERNAL_ERROR).model_dump_json()

    def process_request_object(
        self, json_data: object
    ) -> Optional[Union[ResponseType, ResponseBatch]]:
        result: Optional[Union[ResponseType, ResponseBatch]]
        if isinstance(json_data, list):
            result = ResponseBatch()
            for element in json_data:
                result_element = self._process_single_request(element)
                if result_element is not None:
                    result.append(result_element)
        elif isinstance(json_data, dict):
            result = self._process_single_request(json_data)
        else:
            result = ErrorResponse(
                id=None,
                error=DataError.from_error(INVALID_REQUEST, json_data),
            )
        if result:
            return result
        else:
            return None

    def _process_single_request(
        self, request: dict[str, Any]
    ) -> Union[ResultResponse, ErrorResponse, None]:
        id_ = None
        try:
            id_ = request.get("id")
            method_name = request.get("method")
            if method_name is None:
                return ErrorResponse(
                    id=id_, error=DataError.from_error(INVALID_REQUEST, data=request)
                )
            params = request.get("params")
            method = self._rpc_methods[method_name]
            if isinstance(params, dict):
                result = method(**params)
            elif isinstance(
                params,
                list,
            ):
                result = method(*params)
            else:
                result = method()
            if id_ is not None:
                return ResultResponse(id=id_, result=result)
            else:
                return None
        except Exception as exc:
            log.exception(f"{type(exc).__name__}:", exc_info=exc)
            return ErrorResponse(id=id_, error=SERVER_ERROR)

    def discover(self) -> dict[str, Any]:
        """list all the capabilities of the server."""
        result: dict[str, Any] = {"openrpc": "1.2.6"}
        result["info"] = {"title": self.title, "version": self._version}
        methods: list[dict[str, Any]] = []
        for name, method in self._rpc_methods.items():
            if name == "rpc.discover":
                # do not list it
                continue
            method_dict = {"name": name}
            if method.__doc__:
                lines = method.__doc__.split("\n")
                method_dict["summary"] = lines[0]
                if lines[1:]:
                    method_dict["description"] = " ".join(
                        line.strip() for line in lines[1:] if line
                    ).strip()
            methods.append(method_dict)
        result["methods"] = methods
        return result
