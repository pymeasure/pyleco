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
import types
from unittest.mock import MagicMock, patch

import pytest

from pyleco.core.security import SecurityConfig, SecurityMode
from pyleco.core.zap import start_authenticator, stop_authenticator


def _create_mock_zmq_auth():
    mock_zmq_auth = types.ModuleType("zmq.auth")
    mock_zmq_auth.ThreadAuthenticator = MagicMock()
    mock_zmq_auth.CURVE_ALLOW_ANY = "*"
    mock_zmq_auth_thread = types.ModuleType("zmq.auth.thread")
    mock_zmq_auth_thread.ThreadAuthenticator = mock_zmq_auth.ThreadAuthenticator
    return mock_zmq_auth, mock_zmq_auth_thread


class TestStartAuthenticator:
    @patch("pyleco.core.zap.load_authorized_keys", return_value={})
    def test_any_authenticated_mode(self, mock_load_keys: MagicMock) -> None:
        mock_zmq_auth, mock_zmq_auth_thread = _create_mock_zmq_auth()
        mock_auth = MagicMock()
        mock_zmq_auth.ThreadAuthenticator.return_value = mock_auth
        mock_zmq = types.ModuleType("zmq")
        mock_zmq.auth = mock_zmq_auth
        with patch.dict(
            sys.modules,
            {
                "zmq": mock_zmq,
                "zmq.auth": mock_zmq_auth,
                "zmq.auth.thread": mock_zmq_auth_thread,
            },
        ):
            ctx = MagicMock()
            cfg = SecurityConfig(mode=SecurityMode.CURVE, curve_any_authenticated=True)
            result = start_authenticator(ctx, cfg)
        mock_zmq_auth.ThreadAuthenticator.assert_called_once_with(ctx)
        mock_auth.start.assert_called_once()
        mock_auth.configure_curve.assert_called_once_with(domain="*", location="*")
        assert result is mock_auth
        mock_load_keys.assert_not_called()

    @patch("pyleco.core.zap.load_authorized_keys")
    def test_authorized_keys_dict(self, mock_load_keys: MagicMock) -> None:
        mock_load_keys.return_value = {"N1.Actor1": "a" * 40, "N1.Actor2": "b" * 40}
        mock_zmq_auth, mock_zmq_auth_thread = _create_mock_zmq_auth()
        mock_auth = MagicMock()
        mock_zmq_auth.ThreadAuthenticator.return_value = mock_auth
        mock_zmq = types.ModuleType("zmq")
        mock_zmq.auth = mock_zmq_auth
        with patch.dict(
            sys.modules,
            {
                "zmq": mock_zmq,
                "zmq.auth": mock_zmq_auth,
                "zmq.auth.thread": mock_zmq_auth_thread,
            },
        ):
            ctx = MagicMock()
            cfg = SecurityConfig(
                mode=SecurityMode.CURVE,
                authorized_keys={"N1.Actor1": "a" * 40, "N1.Actor2": "b" * 40},
            )
            result = start_authenticator(ctx, cfg)
        mock_auth.configure_curve_callback.assert_called_once()
        call_kwargs = mock_auth.configure_curve_callback.call_args
        assert call_kwargs[1]["domain"] == "*"
        provider = call_kwargs[1]["credentials_provider"]
        assert provider._authorized_keys == {"N1.Actor1": "a" * 40, "N1.Actor2": "b" * 40}
        mock_load_keys.assert_called_once_with(cfg)
        assert result is mock_auth

    @patch("pyleco.core.zap.load_authorized_keys")
    def test_authorized_keys_dir(self, mock_load_keys: MagicMock, tmp_path) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1.public").write_text("a" * 40)
        mock_load_keys.return_value = {"N1.Actor1": "a" * 40}
        mock_zmq_auth, mock_zmq_auth_thread = _create_mock_zmq_auth()
        mock_auth = MagicMock()
        mock_zmq_auth.ThreadAuthenticator.return_value = mock_auth
        mock_zmq = types.ModuleType("zmq")
        mock_zmq.auth = mock_zmq_auth
        with patch.dict(
            sys.modules,
            {
                "zmq": mock_zmq,
                "zmq.auth": mock_zmq_auth,
                "zmq.auth.thread": mock_zmq_auth_thread,
            },
        ):
            ctx = MagicMock()
            cfg = SecurityConfig(mode=SecurityMode.CURVE, authorized_keys_dir=str(key_dir))
            start_authenticator(ctx, cfg)
        mock_auth.configure_curve_callback.assert_called_once()
        call_kwargs = mock_auth.configure_curve_callback.call_args
        provider = call_kwargs[1]["credentials_provider"]
        assert provider._authorized_keys == {"N1.Actor1": "a" * 40}
        mock_load_keys.assert_called_once_with(cfg)

    @patch("pyleco.core.zap.load_authorized_keys", return_value={})
    def test_no_keys_raises_value_error(self, mock_load_keys: MagicMock) -> None:
        mock_zmq_auth, mock_zmq_auth_thread = _create_mock_zmq_auth()
        mock_auth = MagicMock()
        mock_zmq_auth.ThreadAuthenticator.return_value = mock_auth
        mock_zmq = types.ModuleType("zmq")
        mock_zmq.auth = mock_zmq_auth
        with patch.dict(
            sys.modules,
            {
                "zmq": mock_zmq,
                "zmq.auth": mock_zmq_auth,
                "zmq.auth.thread": mock_zmq_auth_thread,
            },
        ):
            ctx = MagicMock()
            cfg = SecurityConfig(mode=SecurityMode.CURVE)
            with pytest.raises(ValueError, match="authorized_keys"):
                start_authenticator(ctx, cfg)

    def test_raises_for_none_mode(self) -> None:
        with pytest.raises(ValueError, match="CURVE"):
            start_authenticator(MagicMock(), SecurityConfig(mode=SecurityMode.NONE))


class TestStopAuthenticator:
    def test_calls_stop(self) -> None:
        mock_auth = MagicMock()
        stop_authenticator(mock_auth)
        mock_auth.stop.assert_called_once()

    def test_handles_exception(self) -> None:
        mock_auth = MagicMock()
        mock_auth.stop.side_effect = RuntimeError("boom")
        stop_authenticator(mock_auth)
        mock_auth.stop.assert_called_once()
