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

from pyleco.core.data_message import DataMessage

topic = b"N1.CA"
cid = b"conversation_id;"
message_type = 0


@pytest.fixture
def message():
    message = DataMessage(topic, conversation_id=cid, data=[4, 5])
    return message


class TestDataMessageInit:
    def test_topic(self, message: DataMessage):
        assert message.topic == topic

    def test_header(self, message: DataMessage):
        assert message.header == cid + b"\x00"

    def test_data(self, message: DataMessage):
        assert message.data == [4, 5]

    @pytest.mark.parametrize("key, value", (("conversation_id", b"content"),
                                            ("message_type", 7),
                                            ))
    def test_header_param_incompatible_with_header_element_params(self, key, value):
        with pytest.raises(ValueError, match="header"):
            DataMessage(topic="topic", header=b"whatever", **{key: value})

    def test_additional_payload(self):
        message = DataMessage("topic", data=b"0", additional_payload=[b"1", b"2"])
        assert message.payload == [b"0", b"1", b"2"]

    def test_additional_payload_without_data(self):
        message = DataMessage("topic", additional_payload=[b"1", b"2"])
        assert message.payload == [b"1", b"2"]


def test_data_message_str_topic():
    assert DataMessage(topic="topic").topic == b"topic"


def test_data_message_message_type():
    message = DataMessage(topic=b"topic", message_type=7)
    assert message.message_type == 7


def test_converation_id(message: DataMessage):
    assert message.conversation_id == cid


def test_message_type(message: DataMessage):
    assert message.message_type == 0


class TestDataMessageData:
    def test_bytes_payload(self):
        message = DataMessage(b"", data=b"some data stuff")
        assert message.payload == [b"some data stuff"]

    def test_str_payload(self):
        message = DataMessage(b"", data="some data stuff")
        assert message.payload == [b"some data stuff"]

    def test_no_payload(self):
        message = DataMessage(b"")
        assert message.payload == []


class TestFromFrames:
    @pytest.fixture
    def from_frames_message(self):
        message = DataMessage.from_frames(b"frame0", b"frame1", b"frame2", b"frame3")
        return message

    def test_topic(self, from_frames_message: DataMessage):
        assert from_frames_message.topic == b"frame0"

    def test_header(self, from_frames_message: DataMessage):
        assert from_frames_message.header == b"frame1"

    def test_payload(self, from_frames_message: DataMessage):
        assert from_frames_message.payload == [b"frame2", b"frame3"]


def test_to_frames():
    message = DataMessage(b"topic", conversation_id=cid, data=b"data")
    assert message.to_frames() == [b"topic", b"conversation_id;\x00", b"data"]


class TestComparison:
    def test_message_comparison(self):
        frames = [b"topic", b"conversation_id;\x00", b'[["GET", [1, 2]]']
        m1 = DataMessage.from_frames(*frames)
        m2 = DataMessage.from_frames(*frames)
        assert m1 == m2

    def test_dictionary_order_is_irrelevant(self):
        m1 = DataMessage(b"topic", conversation_id=cid, data={"a": 1, "b": 2})
        m2 = DataMessage(b"topic", conversation_id=cid, data={"b": 2, "a": 1})
        assert m1 == m2

    def test_distinguish_empty_payload_frame(self):
        m1 = DataMessage("r", conversation_id=b"conversation_id;")
        m1.payload = [b""]
        m2 = DataMessage("r", conversation_id=b"conversation_id;")
        assert m2.payload == []  # verify that it does not have a payload
        assert m1 != m2

    @pytest.mark.parametrize("other", (5, 3.4, [64, 3], (5, "string"), "string"))
    def test_comparison_with_something_else_fails(self, message, other):
        assert message != other


def test_repr():
    message = DataMessage.from_frames(b'topic', b'conversation_id;\x00', b'data')
    assert repr(message) == r"DataMessage.from_frames(b'topic', b'conversation_id;\x00', b'data')"
