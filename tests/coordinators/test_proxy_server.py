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

"""Hangs infinitely on import on github CI."""

# from __future__ import annotations
# import threading
# from typing import Optional

# import pytest
# import zmq

# from pyleco.core import (
#     PROXY_RECEIVING_PORT,
#     PROXY_SENDING_PORT,
# )
# from pyleco.test import FakeContext, FakeSocket

# from pyleco.coordinators.proxy_server import pub_sub_proxy, start_proxy

# parameters: tuple[FakeSocket, FakeSocket, Optional[FakeSocket]]


# @pytest.fixture
# def fake_proxy_steerable(monkeypatch: pytest.MonkeyPatch) -> None:
#     def _fake_proxy_steerable(
#         frontend: FakeSocket, backend: FakeSocket, capture: Optional[FakeSocket] = None
#     ):
#         global parameters
#         parameters = frontend, backend, capture
#         raise zmq.ContextTerminated

#     monkeypatch.setattr("zmq.proxy_steerable", _fake_proxy_steerable)


# class Test_pub_sub_proxy:
#     def test_default_config(self, fake_proxy_steerable):
#         pub_sub_proxy(FakeContext())  # type: ignore
#         global parameters
#         f, b, c = parameters
#         assert f.addr == f"tcp://*:{PROXY_SENDING_PORT}"
#         assert b.addr == f"tcp://*:{PROXY_RECEIVING_PORT}"
#         assert c is None

#     def test_event_set_for_successful_binding(self, fake_proxy_steerable):
#         event = threading.Event()
#         pub_sub_proxy(FakeContext(), event=event)  # type: ignore
#         assert event.is_set()

#     @pytest.mark.parametrize(
#         "pub, sub",
#         (
#             ("localhost", "remote"),
#             ("remote", "localhost"),
#             ("a", "b"),
#         ),
#     )
#     def test_remote_configuration(self, pub: str, sub: str, fake_proxy_steerable):
#         pub_sub_proxy(FakeContext(), sub=sub, pub=pub)  # type: ignore
#         global parameters
#         f, b, c = parameters
#         assert f.addr == f"tcp://{pub}:{PROXY_RECEIVING_PORT}"
#         assert b.addr == f"tcp://{sub}:{PROXY_SENDING_PORT}"

#     def test_capture(self, fake_proxy_steerable):
#         pub_sub_proxy(context=FakeContext(), captured=True)  # type: ignore
#         global parameters
#         f, b, c = parameters  # type: ignore
#         c: FakeSocket
#         assert c.addr == "inproc://capture"
#         assert c.socket_type == zmq.PUB


# def test_start_proxy():
#     context = start_proxy()
#     # assert no error is raised
#     context.term()


# @pytest.mark.skip(reason="Hangs infinitely")
# def test_start_proxy_fails_if_already_started():
#     # arrange
#     context = start_proxy()
#     with pytest.raises(TimeoutError):
#         start_proxy()
#     # assert no error is raised
#     context.term()
