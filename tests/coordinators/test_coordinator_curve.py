#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2026 PyLECO Developers
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

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from pyleco.core.security import KeyPair, SecurityConfig, SecurityMode


FAKE_PUBLIC = "a" * 40
FAKE_SECRET = "b" * 40
FAKE_SERVER_PUBLIC = "c" * 40


def _make_server_config() -> SecurityConfig:
    return SecurityConfig(
        mode=SecurityMode.CURVE,
        server_key_pair=KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET),
        client_key_pair=KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET),
        server_public_key=FAKE_SERVER_PUBLIC,
    )


class _FakeMultiSocket:
    def __init__(self, *args, **kwargs):
        self._messages_read = []
        self._messages_sent = []
        self.closed = False

    def bind(self, host="", port=0):
        pass

    def unbind(self):
        pass

    def close(self, timeout=0):
        self.closed = True

    def send_message(self, identity, message):
        self._messages_sent.append((identity, message))

    def message_received(self, timeout=0):
        return len(self._messages_read) > 0

    def read_message(self):
        return self._messages_read.pop(0)


_zmq_modules = [
    "zmq",
    "zmq.backend",
    "zmq.backend.cython",
    "zmq.backend.cython._zmq",
    "zmq.sugar",
    "zmq.sugar.constants",
    "zmq.auth",
    "zmq.auth.thread",
]


@pytest.fixture(autouse=True)
def mock_zmq():
    mocks = {}
    for mod_name in _zmq_modules:
        if mod_name not in sys.modules:
            mocks[mod_name] = MagicMock()
            sys.modules[mod_name] = mocks[mod_name]
    yield
    for mod_name in mocks:
        if sys.modules.get(mod_name) is mocks[mod_name]:
            del sys.modules[mod_name]


class TestCoordinatorCurveStartAuthenticator:
    def test_curve_mode_calls_start_authenticator(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        mock_start.return_value = MagicMock()
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            cfg = _make_server_config()
            Coordinator(
                namespace="N1",
                security_config=cfg,
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            mock_start.assert_called_once_with(mock_context, cfg)

    def test_none_mode_does_not_call_start_authenticator(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            Coordinator(
                namespace="N1",
                security_config=SecurityConfig(mode=SecurityMode.NONE),
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            mock_start.assert_not_called()


class TestCoordinatorCurvePassesConfig:
    def test_passes_security_config_to_zmq_multi_socket(self) -> None:
        mock_multi_socket_cls = MagicMock()
        mock_multi_socket = MagicMock()
        mock_multi_socket_cls.return_value = mock_multi_socket
        with patch("pyleco.coordinators.coordinator.ZmqMultiSocket", mock_multi_socket_cls), patch(
            "pyleco.coordinators.coordinator.start_authenticator"
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            cfg = _make_server_config()
            Coordinator(
                namespace="N1",
                security_config=cfg,
                context=mock_context,
            )
            mock_multi_socket_cls.assert_called_once_with(context=mock_context, security_config=cfg)


class TestCoordinatorCurveCloseStopsAuthenticator:
    def test_close_calls_stop_authenticator_when_authenticator_started(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        mock_authenticator = MagicMock()
        mock_start.return_value = mock_authenticator
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            cfg = _make_server_config()
            c = Coordinator(
                namespace="N1",
                security_config=cfg,
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            c.close()
            mock_stop.assert_called_once_with(mock_authenticator)

    def test_close_does_not_call_stop_authenticator_when_none_mode(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            c = Coordinator(
                namespace="N1",
                security_config=SecurityConfig(mode=SecurityMode.NONE),
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            c.close()
            mock_stop.assert_not_called()


class TestCoordinatorStoresSecurityConfig:
    def test_security_config_stored(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        mock_start.return_value = MagicMock()
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            cfg = _make_server_config()
            c = Coordinator(
                namespace="N1",
                security_config=cfg,
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            assert c.security_config is cfg

    def test_none_config_creates_default(self) -> None:
        mock_start = MagicMock()
        mock_stop = MagicMock()
        with patch("pyleco.coordinators.coordinator.start_authenticator", mock_start), patch(
            "pyleco.coordinators.coordinator.stop_authenticator", mock_stop
        ), patch("pyleco.coordinators.coordinator.warn_insecure_mode"):
            from pyleco.coordinators.coordinator import Coordinator

            mock_context = MagicMock()
            c = Coordinator(
                namespace="N1",
                context=mock_context,
                multi_socket=_FakeMultiSocket(),  # type: ignore
            )
            assert c.security_config.mode == SecurityMode.NONE
