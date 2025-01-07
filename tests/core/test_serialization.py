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
import datetime
import uuid
from typing import Any, Optional, Union

import pytest
from pyleco.json_utils.json_objects import Request

from pyleco.core import serialization
from pyleco.core.serialization import JsonContentTypes, get_json_content_type


class Test_create_header_frame:
    @pytest.mark.parametrize("kwargs, header", (
        ({"conversation_id": b"\x00" * 16, }, bytes([0] * 20)),
        ({"conversation_id": b"\x00" * 16, "message_type": b"5"}, bytes([0] * 19) + b"5")
    ))
    def test_create_header_frame(self, kwargs, header):
        assert serialization.create_header_frame(**kwargs) == header

    @pytest.mark.parametrize("cid_l", (0, 1, 2, 4, 6, 7, 10, 15, 17, 20))
    def test_wrong_cid_length_raises_errors(self, cid_l):
        with pytest.raises(ValueError, match="'conversation_id'"):
            serialization.create_header_frame(conversation_id=bytes([0] * cid_l))

    @pytest.mark.parametrize("mid_l", (0, 1, 2, 4, 6, 7))
    def test_wrong_mid_length_raises_errors(self, mid_l):
        with pytest.raises(ValueError, match="'message_id'"):
            serialization.create_header_frame(message_id=bytes([0] * mid_l))

    @pytest.mark.parametrize("mtl", (0, 2, 3))
    def test_wrong_m_type_length_raises_errors(self, mtl):
        with pytest.raises(ValueError, match="'message_type'"):
            serialization.create_header_frame(message_type=bytes([0] * mtl))


@pytest.mark.parametrize("header, conversation_id, message_id, message_type", (
        (bytes(range(20)), bytes(range(16)), b"\x10\x11\x12", 19),
))
def test_interpret_header(header, conversation_id, message_id, message_type):
    assert serialization.interpret_header(header) == (conversation_id, message_id, message_type)


@pytest.mark.parametrize("full_name, node, name", (
    (b"local only", b"node", b"local only"),
    (b"abc.def", b"abc", b"def"),
))
def test_split_name(full_name, node, name):
    assert serialization.split_name(full_name, b"node") == (node, name)


@pytest.mark.parametrize("full_name, node, name", (
    ("local only", "node", "local only"),
    ("abc.def", "abc", "def"),
))
def test_split_name_str(full_name, node, name):
    assert serialization.split_name_str(full_name, "node") == (node, name)


class Test_serialize:
    def test_json_object(self):
        obj = Request(id=3, method="whatever")
        expected = b'{"id":3,"method":"whatever","jsonrpc":"2.0"}'
        assert serialization.serialize_data(obj) == expected

    def test_dict(self):
        raw = {"some": "item", "key": "value", 5: [7, 3.1]}
        expected = b'{"some":"item","key":"value","5":[7,3.1]}'
        assert serialization.serialize_data(raw) == expected


class Test_generate_conversation_id_is_UUIDv7:
    @pytest.fixture
    def conversation_id(self):
        return serialization.generate_conversation_id()

    def test_type_is_bytes(self, conversation_id):
        assert isinstance(conversation_id, bytes)

    def test_length(self, conversation_id):
        assert len(conversation_id) == 16

    def test_UUID_version(self, conversation_id):
        assert conversation_id[6] >> 4 == 7

    def test_variant(self, conversation_id):
        assert conversation_id[8] >> 6 == 0b10

    def test_correct_timestamp(self, conversation_id):
        ts = serialization.conversation_id_to_datetime(conversation_id=conversation_id)
        assert abs(ts - datetime.datetime.now(datetime.timezone.utc)) < datetime.timedelta(hours=1)


def test_conversation_id_to_datetime_according_to_uuid_example():
    """According to the draft https://datatracker.ietf.org/doc/draft-ietf-uuidrev-rfc4122bis/14/
    017F22E2-79B0-7CC3-98C4-DC0C0C07398F should be a timestamp of
    Tuesday, February 22, 2022 2:22:22.00 PM GMT-05:00, represented as 1645557742000
    """
    cid = uuid.UUID("017F22E2-79B0-7CC3-98C4-DC0C0C07398F").bytes
    reference = datetime.datetime(
        2022, 2, 22, 14, 22, 22, tzinfo=datetime.timezone(datetime.timedelta(hours=-5))
    )
    ts = serialization.conversation_id_to_datetime(cid)
    assert reference - ts == datetime.timedelta(0)


def test_json_type_result_is_response():
    assert JsonContentTypes.RESPONSE in JsonContentTypes.RESULT_RESPONSE
    assert JsonContentTypes.RESULT in JsonContentTypes.RESULT_RESPONSE


def test_json_type_error_is_response():
    assert JsonContentTypes.RESPONSE in JsonContentTypes.ERROR_RESPONSE
    assert JsonContentTypes.ERROR in JsonContentTypes.ERROR_RESPONSE


# Methods for get_json_content_type
def create_request(method: str, params: Optional[Union[list, dict]] = None, id: int = 1
                   ) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params}


def create_result(result: Any, id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "result": result, "id": id}


def create_error(error_code: int, error_message: str, id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": error_code, "message": error_message}}


class Test_get_json_content_type:
    @pytest.mark.parametrize("data, type", (
            (create_request("abc"), JsonContentTypes.REQUEST),
            ([create_request(method="abc")] * 2, JsonContentTypes.REQUEST | JsonContentTypes.BATCH),
            (create_result(None), JsonContentTypes.RESULT_RESPONSE),
            ([create_result(None), create_result(5, 7)],
             JsonContentTypes.RESULT_RESPONSE | JsonContentTypes.BATCH),
            (create_error(89, "whatever"), JsonContentTypes.ERROR_RESPONSE),
            ([create_error(89, "xy")] * 2,
             JsonContentTypes.ERROR_RESPONSE | JsonContentTypes.BATCH),
            ([create_result(4), create_error(32, "xy")],  # batch of result and error
             JsonContentTypes.RESULT_RESPONSE | JsonContentTypes.BATCH | JsonContentTypes.ERROR),
    ))
    def test_data_is_valid_type(self, data, type):
        assert get_json_content_type(data) == type

    @pytest.mark.parametrize("data", (
        {},
        [],
        [{}],
        {"some": "thing"},
        5.6,
        "adsfasdf",
    ))
    def test_invalid_data(self, data):
        assert get_json_content_type(data) == JsonContentTypes.INVALID
