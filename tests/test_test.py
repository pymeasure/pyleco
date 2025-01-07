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

from pyleco.test import FakeCommunicator, FakePoller, FakeSocket


@pytest.fixture
def poller() -> FakePoller:
    return FakePoller()


@pytest.fixture
def socket() -> FakeSocket:
    return FakeSocket(1)


@pytest.fixture
def sub_socket() -> FakeSocket:
    return FakeSocket(2)


def test_socket_unbind(socket: FakeSocket):
    socket.bind("abc")
    socket.unbind()
    assert socket.addr is None


def test_socket_disconnect(socket: FakeSocket):
    socket.connect("abc")
    socket.disconnect()
    assert socket.addr is None


@pytest.mark.parametrize("topic", ("string", b"bytes"))
def test_socket_subscribe(sub_socket: FakeSocket, topic):
    sub_socket.subscribe(topic)
    assert isinstance(sub_socket._subscriptions[-1], bytes)


def test_subscribe_fails_for_not_SUB(socket: FakeSocket):
    with pytest.raises(ValueError):
        socket.subscribe("abc")


@pytest.mark.parametrize("topic", ("topic", b"topic"))
def test_socket_unsubscribe(sub_socket: FakeSocket, topic):
    sub_socket._subscriptions.append(b"topic")
    sub_socket.unsubscribe(topic)
    assert b"topic" not in sub_socket._subscriptions


def test_unsubscribe_fails_for_not_SUB(socket: FakeSocket):
    with pytest.raises(ValueError):
        socket.unsubscribe("abc")


class Test_FakePoller_unregister:
    def test_no_error_at_missing(self, poller: FakePoller):
        poller.unregister(FakeSocket(1))
        # assert no error is raised

    def test_unregister_removes_socket(self, poller: FakePoller):
        socket = FakeSocket(1)
        poller._sockets = [1, 2, socket, 4, 5]  # type: ignore
        poller.unregister(socket)
        assert socket not in poller._sockets


def test_FakeCommunicator_sign_in():
    fc = FakeCommunicator("")
    fc.sign_in()
    assert fc._signed_in is True
