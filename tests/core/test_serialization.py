#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
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
from jsonrpcobjects.objects import RequestObject

from pyleco.core import serialization


@pytest.mark.parametrize("kwargs, header", (
    ({}, b";"),
))
def test_create_header_frame(kwargs, header):
    assert serialization.create_header_frame(**kwargs) == header


@pytest.mark.parametrize("full_name, node, name", (
    (b"local only", b"node", b"local only"),
    (b"abc.def", b"abc", b"def"),
))
def test_split_name(full_name, node, name):
    assert serialization.split_name(full_name, b"node") == (node, name)


class Test_serialize:
    def test_json_object(self):
        obj = RequestObject(id=3, method="whatever")
        expected = b'{"id": 3, "method": "whatever", "jsonrpc": "2.0"}'
        assert serialization.serialize_data(obj) == expected

    def test_dict(self):
        raw = {"some": "item", "key": "value", 5: [7, 3.1]}
        expected = b'{"some": "item", "key": "value", "5": [7, 3.1]}'
        assert serialization.serialize_data(raw) == expected
