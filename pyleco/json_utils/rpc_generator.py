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
from typing import Any, Optional, Union

from .json_objects import JsonRpcRequest, JsonRpcResponse
from .json_parser import get_json_object, parse_string
from .errors import ServerError, get_exception_by_code, JSONRPCError, INVALID_SERVER_RESPONSE

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class RPCGenerator:
    """This class can generate a JSONRPC request string and interpret the result string."""

    _id_counter: int = 1

    def build_request_str(self, method: str, *args, **kwargs) -> str:
        params = self.sanitize_params(*args, **kwargs)
        return self.build_json_str(method=method, params=params, id=None)

    @staticmethod
    def sanitize_params(*args, **kwargs) -> Union[dict[str, Any], list[Any], None]:
        if args and kwargs:
            raise ValueError(
                "You may not specify list of positional arguments "
                "and give additional keyword arguments at the same time."
            )
        return kwargs or list(args) or None

    def build_json_str(
        self,
        method: str,
        *,
        notification: bool = False,
        id: Optional[Union[int, str]] = None,
        params: Optional[Union[list, dict]] = None,
    ) -> str:
        """Build JSON-RPC request string.

        :param method: The method name to call
        :param notification: If True, create a notification (no ID)
        :param id: Optional custom ID (only used when notification=False)
        :param params: Optional method parameters
        """
        request_id = None if notification else (id or self._get_next_id())
        return JsonRpcRequest(method=method, params=params, id=request_id).model_dump_json()

    def _get_next_id(self) -> int:
        current_id = self._id_counter
        self._id_counter += 1
        return current_id

    def get_result_from_response(self, data: Union[bytes, str, dict]) -> Any:
        deserialized = parse_string(data) if isinstance(data, (str, bytearray, bytes)) else data

        try:
            json_obj = get_json_object(deserialized)
        except JSONRPCError as exc:
            raise JSONRPCError(INVALID_SERVER_RESPONSE.with_data(deserialized)) from exc

        if not isinstance(json_obj, JsonRpcResponse):
            raise JSONRPCError(INVALID_SERVER_RESPONSE.with_data(deserialized))

        if json_obj.error is not None:
            exception_class = get_exception_by_code(json_obj.error.code) or ServerError
            raise exception_class(json_obj.error)

        return json_obj.result
