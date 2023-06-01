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

from pyleco.utils.communicator import SimpleCommunicator as Communicator
from pyleco.test import FakeSocket


message_tests = (
    ({'receiver': "broker", 'data': [["GET", [1, 2]], ["GET", 3]], 'sender': 's'},
     [VERSION_B, b"broker", b"s", b";", b'[["GET", [1, 2]], ["GET", 3]]']),
    ({'receiver': "someone", 'conversation_id': b"123", 'sender': "ego", 'message_id': b"1"},
     [VERSION_B, b'someone', b'ego', b'123;1']),
    ({'receiver': "router", 'sender': "origin"},
     [VERSION_B, b"router", b"origin", b";"]),
)


def fake_time():
    return 0


def fake_randbytes(n):
    return b"\01" * n


@pytest.fixture()
def fake_counting(monkeypatch):
    monkeypatch.setattr("pyleco.core.serialization.time", fake_time)
    monkeypatch.setattr("pyleco.core.serialization.random.randbytes", fake_randbytes)


# intercom2
class FakeCommunicator(Communicator):
    def open(self):
        self.connection = FakeSocket("")


@pytest.fixture()
def communicator():
    communicator = FakeCommunicator(name="Test")
    communicator._last_beat = 0
    return communicator


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_communicator_send(communicator, kwargs, message, monkeypatch):
    monkeypatch.setattr("pyleco.utils.communicator.perf_counter", fake_time)
    communicator.send(**kwargs)
    assert communicator.connection._s.pop() == message


@pytest.mark.parametrize("kwargs, message", message_tests)
def test_communicator_read(communicator, kwargs, message):
    communicator.connection._r.append(message)
    response = communicator.read()
    assert response.receiver == kwargs.get('receiver').encode()
    assert response.conversation_id == kwargs.get('conversation_id', b"")
    assert response.sender == kwargs.get('sender', "").encode()
    assert response.message_id == kwargs.get('message_id', b"")
    assert response.data == kwargs.get("data")


def test_communicator_sign_in(communicator, fake_counting):
    communicator.connection._r = [[VERSION_B, b"N2.n", b"N2.COORDINATOR",
                                   b"\x00\x00\x00\x00\x00\x00\x00\x00\x01\x01;", b'[["A"]]']]
    communicator.sign_in()
    assert communicator.node == "N2"


def test_communicator_sign_in_fails(communicator, fake_counting):
    communicator.connection._r = [[VERSION_B, b"N2.n", b"N2.COORDINATOR", b"3;", b'[["A"]]']]
    with pytest.raises(AssertionError, match="Answer"):
        communicator.sign_in()
