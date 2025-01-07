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

from typing import Union

import pytest

from pyleco.json_utils.json_objects import ErrorResponse
from pyleco.json_utils.errors import (JSONRPCError, NODE_UNKNOWN, NOT_SIGNED_IN, DUPLICATE_NAME,
                                      RECEIVER_UNKNOWN)

from pyleco.json_utils.rpc_generator import RPCGenerator, INVALID_SERVER_RESPONSE


@pytest.fixture
def generator() -> RPCGenerator:
    return RPCGenerator()


@pytest.mark.parametrize("method, args, kwargs, result", (
        ("meth", (), {}, '{"id":1,"method":"meth","jsonrpc":"2.0"}'),
        ("with args", (5, ), {},
         '{"id":1,"method":"with args","params":[5],"jsonrpc":"2.0"}'),
        ("with kwargs", (), {'kwarg': 7},
         '{"id":1,"method":"with kwargs","params":{"kwarg":7},"jsonrpc":"2.0"}'),
))
def test_build_request_str(generator: RPCGenerator, method: str, args: tuple, kwargs: dict,
                           result: str) -> None:
    assert generator.build_request_str(method, *args, **kwargs) == result


def test_build_request_str_raises_error(generator: RPCGenerator):
    with pytest.raises(ValueError, match="same time"):
        generator.build_request_str("some_method", "argument", keyword="whatever")


@pytest.mark.parametrize("response, result", (
        ('{"id": 5, "result": 7.9, "jsonrpc": "2.0"}', 7.9),
        (b'{"id": 5, "result": 7.9, "jsonrpc": "2.0"}', 7.9),  # bytes version
        ('{"id": 7, "result": null, "jsonrpc": "2.0"}', None),
        ('{"id": 8, "result": [5, 8.9], "jsonrpc": "2.0"}', [5, 8.9]),
        ('{"id": 9, "result": "whatever", "jsonrpc": "2.0"}', "whatever"),
))
def test_get_result_from_response(generator: RPCGenerator, response: Union[bytes, str], result):
    assert generator.get_result_from_response(response) == result


@pytest.mark.parametrize("error", (NOT_SIGNED_IN, NODE_UNKNOWN, DUPLICATE_NAME, RECEIVER_UNKNOWN))
def test_get_result_from_response_raises_suitable_error(generator: RPCGenerator, error):
    with pytest.raises(JSONRPCError) as exc:
        generator.get_result_from_response(ErrorResponse(id=7, error=error).model_dump_json())
    assert exc.value.rpc_error == error


def test_invalid_response_raises_correct_error(generator: RPCGenerator):
    with pytest.raises(JSONRPCError) as exc:
        generator.get_result_from_response(b"\x00")
    error = exc.value.rpc_error
    assert error.code == INVALID_SERVER_RESPONSE.code
    assert error.message == INVALID_SERVER_RESPONSE.message
