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
    request = json_objects.Request(id=5, method="call")
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


def test_error_with_data():
    """Test that the Error object is json serializable."""
    data_error = json_objects.DataError(code=5, message="whatever", data="abc")
    error_response = json_objects.ErrorResponse(id=7, error=data_error)
    assert error_response.model_dump_json() == '{"id":7,"error":{"code":5,"message":"whatever","data":"abc"},"jsonrpc":"2.0"}'  # noqa


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
