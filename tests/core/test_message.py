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

from pyleco.core import VERSION_B
from pyleco.core.serialization import serialize_data

from pyleco.core.message import Message, MessageTypes


cid = b"conversation_id;"


@pytest.fixture
def message() -> Message:
    return Message(
        receiver=b"N1.receiver",
        sender=b"N2.sender",
        data=[["GET", [1, 2]], ["GET", 3]],
        conversation_id=cid,
        message_id=b"mid",
        message_type=int.from_bytes(b"T", byteorder="big")
    )


class Test_Message_create_message:
    def test_payload(self, message: Message):
        assert message.payload == [serialize_data([["GET", [1, 2]], ["GET", 3]])]

    def test_version(self, message: Message):
        assert message.version == VERSION_B

    def test_receiver(self, message: Message):
        assert message.receiver == b"N1.receiver"

    def test_sender(self, message: Message):
        assert message.sender == b"N2.sender"

    def test_header(self, message: Message):
        assert message.header == b"conversation_id;midT"

    def test_to_frames(self, message: Message):
        assert message.to_frames() == [
            VERSION_B,
            b"N1.receiver",
            b"N2.sender",
            b"conversation_id;midT",
            serialize_data([["GET", [1, 2]], ["GET", 3]]),
        ]

    def test_message_without_data_does_not_have_payload_frame(self):
        message = Message(b"N1.receiver", b"N2.sender", conversation_id=b"conversation_id;")
        assert message.payload == []
        assert message.to_frames() == [VERSION_B, b"N1.receiver", b"N2.sender",
                                       b"conversation_id;\x00\x00\x00\x00"]

    def test_message_binary_data(self):
        message = Message(b"N1.receiver", data=b"binary data")
        assert message.payload[0] == b"binary data"

    def test_message_data_str_to_binary_data(self):
        message = Message(b"rec", data="some string")
        assert message.payload[0] == b"some string"

    def test_additional_binary_data(self):
        message = Message(b"rec", data=b"0", additional_payload=[b"1", b"2"])
        assert message.payload == [b"0", b"1", b"2"]

    def test_additional_payload_without_data(self):
        message = Message(b"rec", additional_payload=[b"1", b"2"])
        assert message.payload == [b"1", b"2"]

    @pytest.mark.parametrize("key, value", (("conversation_id", b"content"),
                                            ("message_id", b"mid"),
                                            ("message_type", 7),
                                            ))
    def test_header_param_incompatible_with_header_element_params(self, key, value):
        with pytest.raises(ValueError, match="header"):
            Message(receiver=b"", header=b"whatever", **{key: value})


class Test_Message_from_frames:
    def test_message_from_frames(self, message: Message):
        message.version = b"diff"  # also if the version is different
        assert Message.from_frames(*message.to_frames()) == message

    def test_different_version(self, message: Message):
        message.version = b"diff"  # also if the version is different
        new_message = Message.from_frames(*message.to_frames())
        assert new_message.version == b"diff"

    def test_multiple_payload_frames(self):
        message = Message.from_frames(
            b"\xffo", b"broker", b"", b";", b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"
        )
        assert message.payload == [b'[["GET", [1, 2]], ["GET", 3]]', b"additional stuff"]

    def test_no_payload(self):
        message = Message.from_frames(VERSION_B, b"broker", b"", b"")
        assert message.payload == []


def test_to_frames_without_payload(message: Message):
    message.payload = []
    assert message.to_frames() == [VERSION_B, b"N1.receiver", b"N2.sender",
                                   b"conversation_id;midT"]


class Test_Message_frame_splitting:
    """Test whether the splitting of header/sender/receiver works as expected."""

    def test_receiver_namespace(self, message: Message):
        assert message.receiver_elements.namespace == b"N1"

    def test_receiver_name(self, message: Message):
        assert message.receiver_elements.name == b"receiver"

    def test_sender_namespace(self, message: Message):
        assert message.sender_elements.namespace == b"N2"

    def test_sender_name(self, message: Message):
        assert message.sender_elements.name == b"sender"

    def test_header_conversation_id(self, message: Message):
        assert message.header_elements.conversation_id == cid

    def test_header_message_id(self, message: Message):
        assert message.header_elements.message_id == b"mid"

    def test_header_message_type(self, message: Message):
        assert message.header_elements.message_type == int.from_bytes(b"T", byteorder="big")


class Test_Message_with_string_parameters:
    @pytest.fixture
    def str_message(self) -> Message:
        message = Message(receiver="N2.receiver", sender="N1.sender")
        return message

    def test_receiver_is_bytes(self, str_message: Message):
        assert str_message.receiver == b"N2.receiver"

    def test_sender_is_bytes(self, str_message: Message):
        assert str_message.sender == b"N1.sender"


class Test_Message_data_payload_conversion:
    def test_data_to_payload(self):
        message = Message(b"r", b"s", data=([{5: "1asfd"}], 8), message_type=MessageTypes.JSON)
        assert message.payload == [serialize_data([[{"5": "1asfd"}], 8])]
        assert message.data == [[{'5': "1asfd"}], 8]  # converted to and from json, so modified!

    def test_payload_to_data(self):
        frames = [b"v", b"r", b"s", b"h", b'[["G", ["nodes"]]]', b'p2']
        message = Message.from_frames(*frames)
        assert message.payload == [b'[["G", ["nodes"]]]', b'p2']
        assert message.data == [["G", ["nodes"]]]

    def test_no_payload_is_no_data(self):
        message = Message(b"r")
        message.payload = []  # make sure, that there is no payload
        assert message.data is None


def test_get_frames_list_raises_error_on_empty_sender():
    m = Message(b"r")
    with pytest.raises(ValueError):
        m.to_frames()


class TestComparison:
    def test_message_comparison(self):
        frames = [VERSION_B, b"rec", b"send", b"x;y", b'[["GET", [1, 2]]']
        m1 = Message.from_frames(*frames)
        m2 = Message.from_frames(*frames)
        assert m1 == m2

    def test_dictionary_order_is_irrelevant(self):
        m1 = Message(b"r", conversation_id=cid, data={"a": 1, "b": 2},
                     message_type=MessageTypes.JSON)
        m2 = Message(b"r", conversation_id=cid, data={"b": 2, "a": 1},
                     message_type=MessageTypes.JSON)
        assert m1 == m2

    def test_distinguish_empty_payload_frame(self):
        m1 = Message("r", conversation_id=b"conversation_id;")
        m1.payload = [b""]
        m2 = Message("r", conversation_id=b"conversation_id;")
        assert m2.payload == []  # verify that it does not have a payload
        assert m1 != m2

    @pytest.mark.parametrize("other", (5, 3.4, [64, 3], (5, "string"), "string"))
    def test_comparison_with_something_else_fails(self, message, other):
        assert message != other


def test_repr():
    message = Message.from_frames(b'V', b'rec', b'send', b'cid;mid', b'data')
    assert repr(message) == r"Message.from_frames(b'V', b'rec', b'send', b'cid;mid', b'data')"


def test_repr_without_sender():
    message = Message.from_frames(b'V', b'rec', b'', b'cid;mid', b'data')
    assert repr(message) == r"Message.from_frames(b'V', b'rec', b'', b'cid;mid', b'data')"


def test_conversation_id_getter(message: Message):
    assert message.conversation_id == cid
