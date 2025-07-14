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
from typing import Any, cast, Union

from .errors import InvalidRequest, INVALID_REQUEST, ParseError, PARSE_ERROR
from .json_objects import (
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
    JsonRpcBatch,
    ResultResponse,
    ErrorResponse,
)


def _generate_invalid_request_error(reason: str, data: Any):
    return InvalidRequest(error=INVALID_REQUEST.with_data(data={"reason": reason, "data": data}))


def _get_single_object(deserialized_object: dict) -> Union[JsonRpcRequest, JsonRpcResponse]:
    try:
        keys = deserialized_object.keys()
    except AttributeError as exc:
        raise _generate_invalid_request_error("Object is not a dict", deserialized_object) from exc
    try:
        if "method" in keys:
            return JsonRpcRequest(**deserialized_object)
        elif "result" in keys:
            return ResultResponse(**deserialized_object)
        elif (error_obj := cast(Union[dict, Any], deserialized_object.get("error"))) is not None:
            error = JsonRpcError(**error_obj)
            deserialized_object["error"] = error
            return ErrorResponse(**deserialized_object)
    except (TypeError, ValueError) as exc:
        raise _generate_invalid_request_error(f"TypeError: {exc}", deserialized_object) from exc
    raise _generate_invalid_request_error("Deserialization failed", deserialized_object)


def get_json_object(
    deserialized_object: Union[dict, list, Any],
) -> Union[JsonRpcRequest, JsonRpcResponse, JsonRpcBatch]:
    if isinstance(deserialized_object, list):
        if not deserialized_object:
            raise _generate_invalid_request_error("Empty batch", deserialized_object)
        elements = [_get_single_object(element) for element in deserialized_object]
        batch = JsonRpcBatch(elements)
        if not batch.is_mixed_batch:
            return batch
        raise _generate_invalid_request_error("Mixed batch", deserialized_object)
    elif isinstance(deserialized_object, dict):
        return _get_single_object(deserialized_object)
    else:
        raise _generate_invalid_request_error("Neither list nor dict", deserialized_object)


def parse_string(input: Union[str, bytes]) -> Any:
    try:
        return json.loads(input)
    except Exception as exc:
        raise ParseError(PARSE_ERROR) from exc


def parse_string_into_json_object(
    input: Union[str, bytes],
) -> Union[JsonRpcRequest, JsonRpcResponse, JsonRpcBatch]:
    deserialized = parse_string(input)
    return get_json_object(deserialized)
