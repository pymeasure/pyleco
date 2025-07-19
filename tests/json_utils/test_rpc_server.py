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

import json
import logging

import pytest

from pyleco.json_utils.rpc_generator import RPCGenerator
from pyleco.json_utils.rpc_server import RPCServer
from pyleco.json_utils.json_objects import (
    Request,
    ParamsRequest,
    ResultResponse,
    ErrorResponse,
    ResponseBatch,
    RequestBatch,
    Notification,
    ParamsNotification,
    JsonRpcBatch,
)
from pyleco.json_utils.errors import (
    InternalError,
    INTERNAL_ERROR,
    InvalidParams,
    INVALID_PARAMS,
    InvalidRequest,
    INVALID_REQUEST,
    MethodNotFound,
    METHOD_NOT_FOUND,
    ParseError,
    PARSE_ERROR,
)


@pytest.fixture
def rpc_generator() -> RPCGenerator:
    return RPCGenerator()


args = None
def side_effect_method(arg=None) -> int:
    global args
    args = (arg,)
    return 5


def fail() -> None:
    """Fail always.

    This method fails always.
    And has a description.
    """
    raise NotImplementedError


def fail_TypeError() -> None:
    """Fail with a typing error."""
    raise TypeError("Some error message")


def simple() -> int:
    """A method without parameters."""
    return 7


def obligatory_parameter(arg1: float) -> float:
    """Needs an argument."""
    return arg1 * 2


@pytest.fixture
def rpc_server() -> RPCServer:
    rpc_server = RPCServer()
    rpc_server.method(name="sem")(side_effect_method)
    rpc_server.method()(side_effect_method)
    rpc_server.method()(fail)
    rpc_server.method()(simple)
    rpc_server.method()(fail_TypeError)
    rpc_server.method()(obligatory_parameter)
    return rpc_server


def test_success(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = ParamsRequest(1, method="sem", params=dict(arg=3)).model_dump_json()
    response = rpc_server.process_request(request)
    result = rpc_generator.get_result_from_response(response)  # type: ignore
    assert result == 5
    assert args == (3,)  # type: ignore


def test_multiple_requests_success(rpc_server: RPCServer, rpc_generator: RPCGenerator):
    request1 = ParamsRequest(id=1, method="sem", params=[3])
    request2 = Request(id=2, method="side_effect_method")
    message = RequestBatch([request1, request2]).model_dump_json()
    result = rpc_server.process_request(message)
    result_obj = json.loads(result)  # type: ignore
    assert rpc_generator.get_result_from_response(result_obj[0]) == 5
    assert rpc_generator.get_result_from_response(result_obj[1]) == 5


def test_failing_method(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = Request(1, method="fail").model_dump_json()
    response = rpc_server.process_request(request)
    with pytest.raises(InternalError) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INTERNAL_ERROR.code
    assert error.message == INTERNAL_ERROR.message


def test_failing_parsing_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    response = rpc_server.process_request(b"\x01basdf")
    with pytest.raises(ParseError) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == PARSE_ERROR.code
    assert error.message == PARSE_ERROR.message


def test_method_not_found_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    method_name = "not existing method"
    request = Request(1, method=method_name).model_dump_json()
    response = rpc_server.process_request(request)
    with pytest.raises(MethodNotFound) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == METHOD_NOT_FOUND.code
    assert error.message == METHOD_NOT_FOUND.message
    assert error.data == method_name  # type: ignore


def test_wrong_method_arguments_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    args = {"arg": 9}
    request = ParamsRequest(1, "simple", args)
    response = rpc_server.process_request(request.model_dump_json())
    with pytest.raises(InvalidParams) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INVALID_PARAMS.code
    assert error.message == INVALID_PARAMS.message
    assert error.data == request.model_dump()  # type: ignore


def test_invalid_method_arguments_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    args = "some string"
    request = Request(1, "obligatory_parameter")
    request.params = args  # type: ignore
    response = rpc_server.process_request(request.model_dump_json())
    with pytest.raises(InvalidRequest) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INVALID_REQUEST.code
    assert error.message == INVALID_REQUEST.message
    assert error.data == {
        "reason": "TypeError: Params must be a list, dict, or None",
        "data": request.model_dump(),
    }  # type: ignore


def test_required_parameter_missing_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = Request(1, "obligatory_parameter")
    response = rpc_server.process_request(request.model_dump_json())
    with pytest.raises(InvalidParams) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INVALID_PARAMS.code
    assert error.message == INVALID_PARAMS.message
    assert error.data == request.model_dump()  # type: ignore


def test_process_response_raise_error(rpc_server: RPCServer, rpc_generator: RPCGenerator):
    """It should be a request, not a response!"""
    request = ResultResponse(id=7, result=9)
    request_string = request.model_dump_json()
    response = rpc_server.process_request(request_string)
    with pytest.raises(InvalidRequest) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INVALID_REQUEST.code
    assert error.message == INVALID_REQUEST.message
    assert error.data == {"reason": "Not a request", "data": request.model_dump()}  # type: ignore


@pytest.mark.parametrize(
    "input",
    [
        Notification("simple"),
        ParamsNotification("obligatory_parameter", [5]),
        Notification("obligatory_parameter"),  # would create error message due to invalid params
        Notification("not_existing_method"),  # would create error message due to unknown method
        Notification("fail"),  # would create error message due to failing method
        Notification("fail_TypeError"),
        RequestBatch([Notification("simple"), Notification("fail")]),
    ],
)
def test_notifications_do_not_return_anything(rpc_server: RPCServer, input: Request):
    request_str = input.model_dump_json()
    assert rpc_server.process_request(request_str) is None


class Test_discover_method:

    @pytest.fixture
    def discovered(self, rpc_server: RPCServer, rpc_generator: RPCGenerator) -> dict:
        request = Request(1, "rpc.discover")
        response = rpc_server.process_json_request_object(request)
        assert isinstance(response, ResultResponse)
        return response.result  # type: ignore

    def test_info(self, discovered: dict):
        info: dict = discovered["info"]
        assert info.get("title") == "RPC Server"
        assert info.get("version") == "0.1.0"

    @pytest.fixture
    def methods(self, discovered: dict) -> list:
        return discovered.get("methods")  # type: ignore

    def test_side_effect_method(self, methods: list):
        m1: dict = methods[0]
        m2 = methods[1]
        assert m1["name"] == "sem"
        assert m1.get("description") is None
        assert m2["name"] == "side_effect_method"

    def test_fail(self, methods: list):
        m = methods[2]
        assert m["name"] == "fail"
        assert m["summary"] == "Fail always."
        assert m.get("description") == "This method fails always. And has a description."

    def test_simple_description(self, methods: list):
        m = methods[3]
        assert m["name"] == "simple"
        assert m["summary"] == "A method without parameters."
        assert m.get("description") is None

    def test_rpc_discover_not_listed(self, methods: list):
        for m in methods:
            if m.get("name") == "rpc.discover":
                raise AssertionError("rpc.discover is listed as a method!")


class Test_process_request:
    def test_log_exception(self, rpc_server: RPCServer, caplog: pytest.LogCaptureFixture):
        rpc_server.process_request(b"\xff")
        records = caplog.record_tuples
        assert records[-1] == (
            "pyleco.json_utils.rpc_server",
            logging.ERROR,
            "ParseError causes 'Parse error'.",
        )

    def test_exception_response(self, rpc_server: RPCServer):
        result = rpc_server.process_request(b"\xff")
        assert result == ErrorResponse(id=None, error=PARSE_ERROR).model_dump_json()

    def test_invalid_request(self, rpc_server: RPCServer):
        result = rpc_server.process_request(b"7")
        assert (
            result
            == ErrorResponse(
                id=None,
                error=INVALID_REQUEST.with_data({"reason": "Neither list nor dict", "data": 7}),
            ).model_dump_json()
        )

    def test_batch_entry_notification(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = RequestBatch([Notification("simple"), Request(4, "simple")]).model_dump_json()
        result = json.loads(rpc_server.process_request(requests))  # type: ignore
        assert result == ResponseBatch([ResultResponse(4, 7)]).model_dump()

    def test_batch_of_notifications(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = RequestBatch([Notification("simple"), Notification("simple")]).model_dump_json()
        result = rpc_server.process_request(requests)
        assert result is None

    def test_notification(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = Notification("simple").model_dump_json()
        result = rpc_server.process_request(requests)
        assert result is None


class Test_process_request_object:
    def test_invalid_request(self, rpc_server: RPCServer):
        result = rpc_server.process_request_object(7)
        assert (
            result.model_dump()  # type: ignore
            == ErrorResponse(
                id=None,
                error=INVALID_REQUEST.with_data({"reason": "Neither list nor dict", "data": 7}),
            ).model_dump()
        )

    def test_batch_entry_notification(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = RequestBatch([Notification("simple"), Request(4, "simple")]).model_dump()
        result = rpc_server.process_request_object(requests)
        assert result == JsonRpcBatch([ResultResponse(4, 7)])

    def test_batch_of_notifications(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = RequestBatch([Notification("simple"), Notification("simple")]).model_dump()
        result = rpc_server.process_request_object(requests)
        assert result is None

    def test_notification(self, rpc_server: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = Notification("simple").model_dump()
        result = rpc_server.process_request_object(requests)
        assert result is None


def test_register_method_twice_raises_error(rpc_server: RPCServer):
    rpc_server.method(name="abc")(simple)
    with pytest.raises(ValueError, match="Method name 'abc' already defined."):
        rpc_server.method(name="abc")(obligatory_parameter)


def test_unregister_method(rpc_server: RPCServer):
    rpc_server.method(name="abc")(obligatory_parameter)
    rpc_server.unregister_method("abc")
    rpc_server.method(name="abc")(simple)
    # assert that it raises no error
