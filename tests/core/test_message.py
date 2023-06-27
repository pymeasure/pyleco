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
    def message(self) -> Message:
        return Message.from_frames(b"\xffo", b"rec", b"send", b"x;y",
                                   b'[["GET", [1, 2]], ["GET", 3]]')

    def test_payload(self, message: Message):
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]']

    def test_version(self, message: Message):
        assert message.version == b"\xffo"

    def test_receiver(self, message: Message):
        assert message.receiver == b"rec"

    def test_sender(self, message: Message):
        assert message.sender == b"send"

    def test_header(self, message: Message):
        assert message.header == b"x;y"

    def test_multiple_payload_frames(self):
        message = Message.from_frames(
            b"\xffo", b"broker", b"", b";", b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"
        )
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"]

    def test_no_payload(self):
        message = Message.from_frames(VERSION_B, b"broker", b"", b";")
        assert message.payload == []

    def test_get_frames_list(self, message: Message):
        assert message.get_frames_list() == [b"\xffo", b"rec", b"send", b"x;y",
                                             b'[["GET", [1, 2]], ["GET", 3]]']


class Test_Message_create_message:
    @pytest.fixture
    def message(self) -> Message:
        return Message(
            receiver=b"rec",
            sender=b"send",
            data=[["GET", [1, 2]], ["GET", 3]],
            conversation_id=b"x",
            message_id=b"y",
        )

    def test_payload(self, message: Message):
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]']

    def test_version(self, message: Message):
        assert message.version == VERSION_B

    def test_receiver(self, message: Message):
        assert message.receiver == b"rec"

    def test_sender(self, message: Message):
        assert message.sender == b"send"

    def test_header(self, message: Message):
        assert message.header == b"x;y"

    def test_get_frames_list(self, message: Message):
        assert message.get_frames_list() == [
            VERSION_B,
            b"rec",
            b"send",
            b"x;y",
            b'[["GET", [1, 2]], ["GET", 3]]',
        ]

    def test_get_frames_list_without_payload(self, message: Message):
        message.payload = []
        assert message.get_frames_list() == [VERSION_B, b"rec", b"send", b"x;y"]

    def test_message_without_data_does_not_have_payload_frame(self):
        message = Message(b"rec", "send")
        assert message.payload == []
        assert message.get_frames_list() == [VERSION_B, b"rec", b"send", b";"]

    def test_message_binary_data(self):
        message = Message(b"rec", data=b"binary data")
        assert message.payload[0] == b"binary data"

    def test_message_data_str_to_binary_data(self):
        message = Message(b"rec", data="some string")
        assert message.payload[0] == b"some string"

class Test_Message_with_strings:
    @pytest.fixture
    def str_message(self) -> Message:
        message = Message(receiver="N2.receiver", sender="N1.sender")
        return message

    def test_receiver_is_bytes(self, str_message: Message):
        assert str_message.receiver == b"N2.receiver"

    def test_sender_is_bytes(self, str_message: Message):
        assert str_message.sender == b"N1.sender"

    def test_set_receiver_as_string(self, str_message: Message):
        str_message.receiver_str = "New.Receiver"
        assert str_message.receiver == b"New.Receiver"

    def test_set_sender_as_string(self, str_message: Message):
        str_message.sender_str = "New.Sender"
        assert str_message.sender == b"New.Sender"

    def test_str_return_values(self, str_message: Message):
        assert str_message.receiver_str == "N2.receiver"
        assert str_message.sender_str == "N1.sender"
        assert str_message.receiver_node_str == "N2"
        assert str_message.receiver_name_str == "receiver"
        assert str_message.sender_node_str == "N1"
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


class TestComparison:
    def test_dictionary_order_is_irrelevant(self):
        assert Message(b"r", data={"a": 1, "b": 2}) == Message(b"r", data={"b": 2, "a": 1})

    def test_distinguish_empty_payload_frame(self):
        m1 = Message("r")
        m1.payload = [b""]
        m2 = Message("r")
        assert m2.payload == []  # verify that it does not have a payload
        assert m1 != m2


