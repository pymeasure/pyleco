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
from pyleco.json_utils.rpc_server_definition import RPCServer
from pyleco.json_utils.json_objects import (
    Request,
    ParamsRequest,
    ResultResponse,
    ErrorResponse,
    DataError,
    ResponseBatch,
)
from pyleco.json_utils.errors import (
    ServerError,
    InvalidRequest,
    INVALID_REQUEST,
    SERVER_ERROR,
    INTERNAL_ERROR,
)

try:
    # Load openrpc server for comparison, if available.
    from openrpc import RPCServer as RPCServerOpen  # type: ignore
except ModuleNotFoundError:
    rpc_server_classes: list = [RPCServer]
else:
    rpc_server_classes = [RPCServer, RPCServerOpen]


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


def simple() -> int:
    """A method without parameters."""
    return 7


def obligatory_parameter(arg1: float) -> float:
    """Needs an argument."""
    return arg1 * 2


@pytest.fixture(params=rpc_server_classes)
def rpc_server(request) -> RPCServer:
    rpc_server = request.param()
    rpc_server.method(name="sem")(side_effect_method)
    rpc_server.method()(side_effect_method)
    rpc_server.method()(fail)
    rpc_server.method()(simple)
    rpc_server.method()(obligatory_parameter)
    return rpc_server


@pytest.fixture
def rpc_server_local() -> RPCServer:
    """Create an instance of PyLECO's RPC Server"""
    rpc_server = RPCServer()
    rpc_server.method(name="sem")(side_effect_method)
    rpc_server.method()(side_effect_method)
    rpc_server.method()(fail)
    rpc_server.method()(simple)
    rpc_server.method()(obligatory_parameter)
    return rpc_server


def test_success(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = rpc_generator.build_request_str(method="sem", arg=3)
    response = rpc_server.process_request(request)
    result = rpc_generator.get_result_from_response(response)  # type: ignore
    assert result == 5
    assert args == (3,)  # type: ignore


def test_multiple_requests_success(rpc_server: RPCServer, rpc_generator: RPCGenerator):
    request1 = ParamsRequest(id=1, method="sem", params=[3])
    request2 = Request(id=2, method="side_effect_method")
    message = json.dumps([request1.model_dump(), request2.model_dump()])
    result = rpc_server.process_request(message)
    result_obj = json.loads(result)  # type: ignore
    assert rpc_generator.get_result_from_response(result_obj[0]) == 5
    assert rpc_generator.get_result_from_response(result_obj[1]) == 5


def test_failing_method(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = rpc_generator.build_request_str(method="fail")
    response = rpc_server.process_request(request)
    with pytest.raises(ServerError) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == SERVER_ERROR.code
    assert error.message == SERVER_ERROR.message


@pytest.mark.xfail(True, reason="Self written RPCServer cannot handle additional args")
def test_wrong_method_arguments_are_ignored(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = rpc_generator.build_request_str(method="simple", arg=9)
    response = rpc_server.process_request(request)
    result = rpc_generator.get_result_from_response(response)  # type: ignore
    assert result == 7


def test_wrong_method_arguments_raise_error(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    if len(rpc_server_classes) > 1 and isinstance(rpc_server, RPCServerOpen):
        pytest.skip(reason="RPCServerOpen does not raise error for wrong arguments")
    request = rpc_generator.build_request_str(method="simple", arg=9)
    response = rpc_server.process_request(request)
    response_obj = json.loads(response)  # type: ignore
    expected_response_obj = ErrorResponse(id=1, error=SERVER_ERROR)
    assert response_obj == expected_response_obj.model_dump()


def test_obligatory_parameter_missing(rpc_generator: RPCGenerator, rpc_server: RPCServer):
    request = rpc_generator.build_request_str(method="obligatory_parameter")
    response = rpc_server.process_request(request)
    with pytest.raises(ServerError) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == SERVER_ERROR.code
    assert error.message == SERVER_ERROR.message


def test_process_response(rpc_server: RPCServer, rpc_generator: RPCGenerator):
    """It should be a request, not a response!"""
    request = ResultResponse(id=7, result=9)
    request_string = request.model_dump_json()
    response = rpc_server.process_request(request_string)
    with pytest.raises(InvalidRequest) as exc_info:
        rpc_generator.get_result_from_response(response)  # type: ignore
    error = exc_info.value.rpc_error
    assert error.code == INVALID_REQUEST.code
    assert error.message == INVALID_REQUEST.message
    # ignore the following test, which depends on the openrpc version
    # assert error.data == request.model_dump()  # type: ignore


class Test_discover_method:

    @pytest.fixture
    def discovered(self, rpc_server: RPCServer, rpc_generator: RPCGenerator) -> dict:
        request = rpc_generator.build_request_str("rpc.discover")
        response = rpc_server.process_request(request)
        return rpc_generator.get_result_from_response(response)  # type: ignore

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


# tests regarding the local implementation of the RPC Server
def test_process_single_notification(rpc_server_local: RPCServer):
    result = rpc_server_local._process_single_request(
        {"jsonrpc": "2.0", "method": "simple"}
    )
    assert result is None


class Test_process_request:
    def test_log_exception(self, rpc_server_local: RPCServer, caplog: pytest.LogCaptureFixture):
        rpc_server_local.process_request(b"\xff")
        records = caplog.record_tuples
        assert records[-1] == (
            "pyleco.json_utils.rpc_server_definition",
            logging.ERROR,
            "UnicodeDecodeError:",
        )

    def test_exception_response(self, rpc_server_local: RPCServer):
        result = rpc_server_local.process_request(b"\xff")
        assert result == ErrorResponse(id=None, error=INTERNAL_ERROR).model_dump_json()

    def test_invalid_request(self, rpc_server_local: RPCServer):
        result = rpc_server_local.process_request(b"7")
        assert (
            result
            == ErrorResponse(
                id=None, error=DataError.from_error(INVALID_REQUEST, 7)
            ).model_dump_json()
        )

    def test_batch_entry_notification(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
            {"jsonrpc": "2.0", "method": "simple", "id": 4},
        ]
        result = json.loads(rpc_server_local.process_request(json.dumps(requests)))  # type: ignore
        assert result == [{"jsonrpc": "2.0", "result": 7, "id": 4}]

    def test_batch_of_notifications(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
            {"jsonrpc": "2.0", "method": "simple"},
        ]
        result = rpc_server_local.process_request(json.dumps(requests))
        assert result is None

    def test_notification(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
        ]
        result = rpc_server_local.process_request(json.dumps(requests))
        assert result is None


class Test_process_request_object:
    def test_invalid_request(self, rpc_server_local: RPCServer):
        result = rpc_server_local.process_request_object(7)
        assert (
            result
            == ErrorResponse(
                id=None, error=DataError.from_error(INVALID_REQUEST, 7)
            )
        )

    def test_batch_entry_notification(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
            {"jsonrpc": "2.0", "method": "simple", "id": 4},
        ]
        result = rpc_server_local.process_request_object(requests)
        assert result == ResponseBatch([ResultResponse(4, 7)])

    def test_batch_of_notifications(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
            {"jsonrpc": "2.0", "method": "simple"},
        ]
        result = rpc_server_local.process_request_object(requests)
        assert result is None

    def test_notification(self, rpc_server_local: RPCServer):
        """A notification (request without id) shall not return anything."""
        requests = [
            {"jsonrpc": "2.0", "method": "simple"},
        ]
        result = rpc_server_local.process_request_object(requests)
        assert result is None
