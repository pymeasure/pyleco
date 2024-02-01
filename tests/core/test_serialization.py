#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2024 PyLECO Developers
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
from jsonrpcobjects.objects import Request

from pyleco.core import serialization


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
