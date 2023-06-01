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

from pyleco.core.message import Message


class Test_Message_from_frames:
    @pytest.fixture
    def message(self):
        return Message.from_frames(b"\xffo", b"rec", b"send", b"x;y",
                                   b'[["GET", [1, 2]], ["GET", 3]]')

    def test_payload(self, message):
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]']

    def test_version(self, message):
        assert message.version == b"\xffo"

    def test_receiver(self, message):
        assert message.receiver == b"rec"

    def test_sender(self, message):
        assert message.sender == b"send"

    def test_header(self, message):
        assert message.header == b"x;y"

    def test_multi_payload(self):
        message = Message.from_frames(
            b"\xffo", b"broker", b"", b";", b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"
        )
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"]

    def test_no_payload(self):
        message = Message.from_frames(VERSION_B, b"broker", b"", b";")
        assert message.payload == []

    def test_get_frames_list(self, message):
        assert message.get_frames_list() == [b"\xffo", b"rec", b"send", b"x;y",
                                             b'[["GET", [1, 2]], ["GET", 3]]']


class Test_Message_create_message:
    @pytest.fixture
    def message(self):
        return Message(
            receiver=b"rec",
            sender=b"send",
            data=[["GET", [1, 2]], ["GET", 3]],
            conversation_id=b"x",
            message_id=b"y",
        )

    def test_payload(self, message):
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]']

    def test_version(self, message):
        assert message.version == VERSION_B

    def test_receiver(self, message):
        assert message.receiver == b"rec"

    def test_sender(self, message):
        assert message.sender == b"send"

    def test_header(self, message):
        assert message.header == b"x;y"

    def test_get_frames_list(self, message):
        assert message.get_frames_list() == [
            VERSION_B,
            b"rec",
            b"send",
            b"x;y",
            b'[["GET", [1, 2]], ["GET", 3]]',
        ]

    def test_get_frames_list_without_payload(self, message):
        message.payload = []
        assert message.get_frames_list() == [VERSION_B, b"rec", b"send", b"x;y"]


class Test_Message_with_strings:
    @pytest.fixture
    def str_message(self):
        message = Message("N2.receiver", "N1.sender")
        return message

    def test_receiver_is_bytes(self, str_message):
        assert str_message.receiver == b"N2.receiver"

    def test_sender_is_bytes(self, str_message):
        assert str_message.sender == b"N1.sender"

    def test_str_return_values(self, str_message):
        assert str_message.receiver_str == "N2.receiver"
        assert str_message.sender_str == "N1.sender"
        assert str_message.receiver_node_str == "N2"
        assert str_message.sender_name_str == "sender"


class Test_Message_data_payload_conversion:
    def test_data_to_payload(self):
        message = Message(b"r", b"s", data=([{5: "1asfd"}], 8))
        assert message.payload == [b'[[{"5": "1asfd"}], 8]']
        assert message.data == ([{5: "1asfd"}], 8)

    def test_payload_to_data(self):
        message = Message.from_frames(b"v", b"r", b"s", b"h", b'[["G", ["nodes"]]]', b'p2')
        assert message.payload == [b'[["G", ["nodes"]]]', b'p2']
        assert message.data == [["G", ["nodes"]]]


def test_message_comparison():
    m1 = Message.from_frames(VERSION_B, b"rec", b"send", b"x;y", b'[["GET", [1, 2]]')
    m2 = Message.from_frames(VERSION_B, b"rec", b"send", b"x;y", b'[["GET", [1, 2]]')
    assert m1 == m2


@pytest.mark.parametrize("property", ("receiver", "sender", "header"))
def test_set_property_resets_cache(property):
    m = Message(b"r")
    setattr(m, f"_{property}_elements", [b"some", b"value"])
    setattr(m, property, b"new value")
    assert getattr(m, f"_{property}_elements") is None


def test_get_frames_list_raises_error_on_empty_sender():
    m = Message(b"r")
    with pytest.raises(ValueError):
        m.get_frames_list()
