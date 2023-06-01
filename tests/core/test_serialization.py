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

from pyleco.core import VERSION_B

from pyleco.core import serialization


message_tests = (
    ({'receiver': "broker", 'data': [["GET", [1, 2]], ["GET", 3]], 'sender': 's'},
     [VERSION_B, b"broker", b"s", b";", b'[["GET", [1, 2]], ["GET", 3]]']),
    ({'receiver': "someone", 'conversation_id': b"123", 'sender': "ego", 'message_id': b"1"},
     [VERSION_B, b'someone', b'ego', b'123;1']),
    ({'receiver': "router", 'sender': "origin"},
     [VERSION_B, b"router", b"origin", b";"]),
)


@pytest.mark.parametrize("kwargs, header", (
    ({}, b";"),
))
def test_create_header_frame(kwargs, header):
    assert serialization.create_header_frame(**kwargs) == header


@pytest.mark.parametrize("kwargs, message", (
    ({'receiver': b"receiver"}, [VERSION_B, b"receiver", b"", b";"]),
    ({'receiver': b"receiver", "payload": [b"abc"]}, [VERSION_B, b"receiver", b"", b";", b"abc"]),
    ({'receiver': b"receiver", "payload": b"abc"}, [VERSION_B, b"receiver", b"", b";", b"abc"]),
    ({'receiver': b"r", 'payload': [b"xyz"], "message_id": b"7"},
     [VERSION_B, b"r", b"", b";7", b"xyz"]),
))
def test_create_message(kwargs, message):
    assert serialization.create_message(**kwargs) == message


@pytest.mark.parametrize("full_name, node, name", (
    (b"local only", b"node", b"local only"),
    (b"abc.def", b"abc", b"def"),
))
def test_split_name(full_name, node, name):
    assert serialization.split_name(full_name, b"node") == (node, name)


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_compose_message(kwargs, message):
    assert serialization.compose_message(**kwargs) == message


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_split_message(kwargs, message):
    receiver, sender, conversation_id, message_id, data = serialization.split_message(message)
    assert receiver == kwargs.get('receiver')
    assert conversation_id == kwargs.get('conversation_id', b"")
    assert sender == kwargs.get('sender', "")
    assert message_id == kwargs.get('message_id', b"")
    assert data == kwargs.get("data")
