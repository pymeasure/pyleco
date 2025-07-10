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

from pyleco.json_utils import json_objects


def test_request():
    request = json_objects.Request(id=5, method="call", jsonrpc="2.0")
    assert request.model_dump() == {
        "id": 5,
        "jsonrpc": "2.0",
        "method": "call",
    }


def test_request_with_positional_arguments():
    request = json_objects.Request(5, "call", "2.0")
    assert request.model_dump() == {
        "id": 5,
        "jsonrpc": "2.0",
        "method": "call",
    }


def test_request_with_params():
    request = json_objects.ParamsRequest(id=5, method="call", params=[1, 5])
    assert request.model_dump() == {
        "id": 5,
        "jsonrpc": "2.0",
        "method": "call",
        "params": [1, 5],
    }


def test_notification():
    request = json_objects.Notification(method="call")
    assert request.model_dump() == {
        "jsonrpc": "2.0",
        "method": "call",
    }


def test_notification_with_params():
    request = json_objects.ParamsNotification(method="call", params=[1, 5])
    assert request.model_dump() == {
        "jsonrpc": "2.0",
        "method": "call",
        "params": [1, 5],
    }


def test_result():
    result = json_objects.ResultResponse(id=5, result=7)
    assert result.model_dump() == {
        "id": 5,
        "jsonrpc": "2.0",
        "result": 7,
    }


def test_result_null():
    result = json_objects.ResultResponse(id=5, result=None)
    assert result.model_dump() == {
        "id": 5,
        "result": None,
        "jsonrpc": "2.0",
    }


def test_error_with_data():
    """Test that the Error object is json serializable."""
    data_error = json_objects.DataError(code=5, message="whatever", data="abc")
    error_response = json_objects.ErrorResponse(id=7, error=data_error)
    assert error_response.model_dump() == {
        "id": 7,
        "error": {"code": 5, "message": "whatever", "data": "abc"},
        "jsonrpc": "2.0",
    }


def test_generate_data_error_from_error():
    error = json_objects.Error(code=5, message="abc")
    data_error = json_objects.DataError.from_error(error, "data")
    assert data_error.code == error.code
    assert data_error.message == error.message
    assert data_error.data == "data"


class Test_BatchObject:
    element = json_objects.Request(5, "start")

    @pytest.fixture
    def batch_obj(self):
        return json_objects.BatchObject([self.element])

    def test_init_with_value(self):
        obj = json_objects.BatchObject([self.element])
        assert obj == [self.element]

    def test_init_with_values(self):
        obj = json_objects.BatchObject([self.element, self.element])
        assert obj == [self.element, self.element]

    def test_bool_value_with_element(self):
        obj = json_objects.BatchObject([self.element])
        assert bool(obj) is True

    def test_bool_value_without_element(self):
        obj = json_objects.BatchObject()
        assert bool(obj) is False

    def test_append(self, batch_obj: json_objects.BatchObject):
        el2 = json_objects.Request(5, "start")
        batch_obj.append(el2)
        assert batch_obj[-1] == el2

    def test_model_dump(self, batch_obj: json_objects.BatchObject):
        assert batch_obj.model_dump() == [self.element.model_dump()]

    def test_model_dump_json(self, batch_obj: json_objects.BatchObject):
        result = '[{"id":5,"method":"start","jsonrpc":"2.0"}]'
        assert batch_obj.model_dump_json() == result


class TestJsonRpcBatch:
    @pytest.fixture
    def request_batch(self):
        return json_objects.JsonRpcBatch(
            [json_objects.Request(id=1, method="req1"), json_objects.Request(id=2, method="req2")]
        )

    @pytest.fixture
    def response_batch(self):
        return json_objects.JsonRpcBatch(
            [
                json_objects.ResultResponse(id=1, result="res1"),
                json_objects.ResultResponse(id=2, result="res2"),
            ]
        )

    @pytest.fixture
    def mixed_batch(self):
        return json_objects.JsonRpcBatch(
            [
                json_objects.Request(id=1, method="req1"),
                json_objects.ResultResponse(id=2, result="res2"),  # type: ignore
            ]
        )

    @pytest.mark.parametrize(
        "batch_fixture, expected_type",
        [
            ("request_batch", json_objects.BatchContentType.REQUESTS),
            ("response_batch", json_objects.BatchContentType.RESPONSES),
            ("mixed_batch", json_objects.BatchContentType.MIXED),
        ]
    )
    def test_batch_type(self, batch_fixture, expected_type, request):
        batch = request.getfixturevalue(batch_fixture)
        assert batch.batch_type == expected_type

    @pytest.mark.parametrize(
        "batch_fixture, is_request, is_response, is_mixed",
        [
            ("request_batch", True, False, False),
            ("response_batch", False, True, False),
            ("mixed_batch", False, False, True),
        ]
    )
    def test_batch_flags(self, batch_fixture, is_request, is_response, is_mixed, request):
        batch = request.getfixturevalue(batch_fixture)
        assert batch.is_request_batch is is_request
        assert batch.is_response_batch is is_response
        assert batch.is_mixed_batch is is_mixed

    def test_notifications_count(self):
        batch = json_objects.JsonRpcBatch(
            [
                json_objects.Request(id=1, method="req1"),
                json_objects.Notification(method="notif1"),
                json_objects.Notification(method="notif2"),
            ]
        )
        assert len(batch.notifications) == 2

    def test_notifications_are_notifications(self):
        batch = json_objects.JsonRpcBatch(
            [
                json_objects.Request(id=1, method="req1"),
                json_objects.Notification(method="notif1"),
            ]
        )
        assert all(n.is_notification for n in batch.notifications)

    def test_get_request_by_id_exists(self, request_batch):
        req = request_batch.get_request_by_id(2)
        assert req is not None

    def test_get_request_method(self, request_batch):
        req = request_batch.get_request_by_id(2)
        assert req.method == "req2"

    def test_get_response_by_id_exists(self, response_batch):
        resp = response_batch.get_response_by_id(1)
        assert resp is not None

    def test_get_response_result(self, response_batch):
        resp = response_batch.get_response_by_id(1)
        assert resp.result == "res1"

    def test_empty_batch_raises_error(self):
        with pytest.raises(ValueError, match="Batch must contain at least one item"):
            json_objects.JsonRpcBatch([])

    def test_invalid_item_type_raises_error(self):
        with pytest.raises(
            ValueError, match="All batch items must be JsonRpcRequest or JsonRpcResponse"
        ):
            json_objects.JsonRpcBatch([{"invalid": "item"}])  # type: ignore


def test_request_validation():
    with pytest.raises(ValueError, match="Method must be a non-empty string"):
        json_objects.Request(id=1, method="")

    with pytest.raises(ValueError, match="Params must be a list, dict, or None"):
        json_objects.ParamsRequest(id=1, method="m", params="invalid")  # type: ignore

    with pytest.raises(ValueError, match="ID must be a string, int, or None"):
        json_objects.Request(id=1.5, method="m")  # type: ignore


def test_response_validation():
    with pytest.raises(ValueError, match="Response cannot have both result and error"):
        json_objects.JsonRpcResponse(
            id=1, result="ok", error=json_objects.Error(code=1, message="err")
        )

    with pytest.raises(ValueError, match="ID must be a string, int, or None"):
        json_objects.ResultResponse(id=1.5, result="res")  # type: ignore


def test_error_with_data_method():
    error = json_objects.JsonRpcError(code=1, message="base")
    data_error = error.with_data("additional info")
    assert data_error.data == "additional info"
    assert data_error.code == error.code
    assert data_error.message == error.message
