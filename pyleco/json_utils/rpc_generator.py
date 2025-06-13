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
from typing import Any, Literal, Optional, Union

from .json_objects import (
    Notification,
    ParamsNotification,
    Request,
    ParamsRequest,
    DataError,
    Error,
    ResultResponse,
    RequestType,
)
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
        id: Union[Literal[False], None, int, str]= None,
        params: Optional[Union[list, dict]] = None,
    ) -> str:
        """Build a JSON-RPC notification (`id is False`) or request string."""
        r: RequestType
        if id is False:
            r = Notification(method) if params is None else ParamsNotification(method, params)
        else:
            if id is None:
                id = self._id_counter
                self._id_counter += 1
            r = Request(id, method) if params is None else ParamsRequest(id, method, params)
        return r.model_dump_json()

    def get_result_from_response(self, data: Union[bytes, str, dict]) -> Any:
        """Get the result of that object or raise an error."""
        # copied from jsonrpc2-pyclient and modified
        try:
            # Parse string to JSON.
            if not isinstance(data, dict):
                json_data = json.loads(data)
            else:
                json_data = data

            # Raise error if JSON RPC error response.
            if error_content := json_data.get("error"):
                error: Union[Error, DataError]
                if "data" in error_content.keys():
                    error = DataError(**error_content)
                else:
                    error = Error(**error_content)
                exc = get_exception_by_code(error.code) or ServerError
                raise exc(error)

            # Return result if JSON RPC result response.
            if "result" in json_data.keys():
                return ResultResponse(**json_data).result

            # Not valid JSON RPC response if it has no error or result.
            raise JSONRPCError(
                DataError(
                    code=INVALID_SERVER_RESPONSE.code,
                    message=INVALID_SERVER_RESPONSE.message,
                    data=json_data,
                )
            )
        except (json.JSONDecodeError, TypeError, AttributeError) as exc:
            log.exception(f"{type(exc).__name__}:")
            raise JSONRPCError(
                DataError(
                    code=INVALID_SERVER_RESPONSE.code,
                    message=INVALID_SERVER_RESPONSE.message,
                    data=data,
                )
            ) from exc
