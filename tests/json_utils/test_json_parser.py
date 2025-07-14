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

import pytest

from pyleco.json_utils.json_objects import (
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcBatch,
    Request,
    ResultResponse,
)
from pyleco.json_utils.errors import InvalidRequest, ParseError, METHOD_NOT_FOUND

from pyleco.json_utils.json_parser import get_json_object, parse_string_into_json_object


def test_parse_request():
    request_data = {"id": 1, "method": "exampleMethod", "jsonrpc": "2.0"}
    parsed_object = get_json_object(request_data)
    assert parsed_object == JsonRpcRequest("exampleMethod", id=1)


def test_parse_params_request():
    params_request_data = {
        "id": 1,
        "method": "exampleMethod",
        "params": {"key": "value"},
        "jsonrpc": "2.0",
    }
    parsed_object = get_json_object(params_request_data)
    assert parsed_object == JsonRpcRequest(id=1, method="exampleMethod", params={"key": "value"})


def test_parse_notification():
    notification_data = {"method": "exampleNotification", "jsonrpc": "2.0"}
    parsed_object = get_json_object(notification_data)
    assert parsed_object == JsonRpcRequest("exampleNotification", id=None)
    assert parsed_object.is_notification is True  # type: ignore


def test_parse_params_notification():
    params_notification_data = {
        "method": "exampleNotification",
        "params": {"key": "value"},
        "jsonrpc": "2.0",
    }
    parsed_object = get_json_object(params_notification_data)
    assert parsed_object == JsonRpcRequest("exampleNotification", params={"key": "value"}, id=None)
    assert parsed_object.is_notification is True  # type: ignore


def test_parse_result_response():
    result_response_data = {"id": 1, "result": {"key": "value"}, "jsonrpc": "2.0"}
    parsed_object = get_json_object(result_response_data)
    assert parsed_object.model_dump() == JsonRpcResponse(id=1, result={"key": "value"}).model_dump()


def test_parse_error_response():
    error_response_data = {
        "id": 1,
        "error": {"code": -32601, "message": "Method not found"},
        "jsonrpc": "2.0",
    }
    parsed_object = get_json_object(error_response_data)
    assert parsed_object.model_dump() == JsonRpcResponse(id=1, error=METHOD_NOT_FOUND).model_dump()


def test_parse_data_error_response():
    error_response_data = {
        "id": 1,
        "error": {"code": -32601, "message": "Method not found", "data": "missing_method"},
        "jsonrpc": "2.0",
    }
    parsed_object = get_json_object(error_response_data)
    assert parsed_object.model_dump() == JsonRpcResponse(
        id=1, error=METHOD_NOT_FOUND.with_data("missing_method")
    ).model_dump()


def test_parse_request_batch():
    request_batch_data = [
        {"id": 1, "method": "exampleMethod1", "jsonrpc": "2.0"},
        {"method": "exampleMethod1", "jsonrpc": "2.0"},
        {"id": 2, "method": "exampleMethod2", "params": {"key": "value"}, "jsonrpc": "2.0"},
    ]
    parsed_object = get_json_object(request_batch_data)
    assert parsed_object == JsonRpcBatch(
        [
            JsonRpcRequest("exampleMethod1", id=1),
            JsonRpcRequest("exampleMethod1", id=None),
            JsonRpcRequest("exampleMethod2", params={"key": "value"}, id=2),
        ]
    )


def test_parse_response_batch():
    response_batch_data = [
        {"id": 1, "result": {"key": "value1"}, "jsonrpc": "2.0"},
        {"id": 2, "error": {"code": -32601, "message": "Method not found"}, "jsonrpc": "2.0"},
    ]
    parsed_object = get_json_object(response_batch_data)
    assert parsed_object.model_dump() == JsonRpcBatch([
        JsonRpcResponse(1, {"key": "value1"}),
        JsonRpcResponse(2, error=METHOD_NOT_FOUND),
    ]).model_dump()


@pytest.mark.parametrize(
    "invalid_data",
    (
        {"invalid_key": "invalid_value", "jsonrpc": "2.0"},
        # {"id": 1, "method": "exampleMethod1"},  # works, TODO should it?
        {"id": 1, "method": "exampleMethod1", "jsonrpc": "2.0", "result": 5},
        {"id": 1, "method": "exampleMethod1", "jsonrpc": "2.0", "error": 5},
        {"id": 1, "result": "exampleMethod1", "jsonrpc": "2.0", "error": 5},
        # [],  # works as it is a valid (empty) batch
        [[]],
        [5],
        5,
        "whatever",
        [Request(1, "method").model_dump(), ResultResponse(1, "result").model_dump()],
    ),
)
def test_parse_invalid_objects(invalid_data):
    with pytest.raises(InvalidRequest):
        get_json_object(invalid_data)

@pytest.mark.parametrize(
    "invalid_data",
    (
        {"id": 1, "method": "exampleMethod", "jsonrpc": "3.0"},
        {"id": 1, "method": 567, "jsonrpc": "2.0"},
        {"id": 1, "method": "exampleMethod", "params": 5, "jsonrpc": "2.0"},
    ),
)
@pytest.mark.xfail(reason="No type checking done.")
def test_parse_invalidly_typed_objects(invalid_data):
    with pytest.raises(InvalidRequest):
        get_json_object(invalid_data)


@pytest.mark.parametrize(
    "string, object",
    (
        (
            '{"id": 1, "method": "exampleMethod", "jsonrpc": "2.0"}',
            JsonRpcRequest(id=1, method="exampleMethod"),
        ),
        ('{"id": 1, "result": 5.6, "jsonrpc": "2.0"}', JsonRpcResponse(1, 5.6)),
    ),
)
def test_parse_string_into_json_object(string: str, object):
    assert parse_string_into_json_object(string).model_dump() == object.model_dump()



@pytest.mark.parametrize("string", (
        '\x01 invalid ASCII',
        "\xfa another invalid ASCII",
        "[array without closure",
))
def test_parse_string_into_json_object_raises_parse_error(string: str):
    with pytest.raises(ParseError):
        parse_string_into_json_object(string)
