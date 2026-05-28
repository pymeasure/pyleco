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

from unittest.mock import MagicMock, patch

import pytest

from pyleco.core.security import KeyPair, ServerSecurityConfig, FullSecurityConfig
from pyleco.core.zap import start_authenticator, stop_authenticator


class TestStartAuthenticator:
    @patch("pyleco.core.zap.load_authorized_keys", return_value={})
    @patch("pyleco.core.zap.ThreadAuthenticator")
    @patch("pyleco.core.zap.CURVE_ALLOW_ANY", "*")
    def test_any_authenticated_mode(
        self, mock_thread_auth_cls: MagicMock, mock_load_keys: MagicMock
    ) -> None:
        mock_auth = MagicMock()
        mock_thread_auth_cls.return_value = mock_auth
        ctx = MagicMock()
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, curve_any_authenticated=True)
        result = start_authenticator(ctx, cfg)
        mock_thread_auth_cls.assert_called_once_with(ctx)
        mock_auth.start.assert_called_once()
        mock_auth.configure_curve.assert_called_once_with(domain="*", location="*")
        assert result is mock_auth
        mock_load_keys.assert_not_called()

    @patch("pyleco.core.zap.load_authorized_keys")
    @patch("pyleco.core.zap.ThreadAuthenticator")
    def test_authorized_keys_dict(
        self, mock_thread_auth_cls: MagicMock, mock_load_keys: MagicMock
    ) -> None:
        mock_load_keys.return_value = {"N1.Actor1": "a" * 40, "N1.Actor2": "b" * 40}
        mock_auth = MagicMock()
        mock_thread_auth_cls.return_value = mock_auth
        ctx = MagicMock()
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(
            server_key_pair=kp,
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
    @patch("pyleco.core.zap.ThreadAuthenticator")
    def test_authorized_keys_dir(
        self, mock_thread_auth_cls: MagicMock, mock_load_keys: MagicMock, tmp_path
    ) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1.public").write_text("a" * 40)
        mock_load_keys.return_value = {"N1.Actor1": "a" * 40}
        mock_auth = MagicMock()
        mock_thread_auth_cls.return_value = mock_auth
        ctx = MagicMock()
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys_dir=str(key_dir))
        start_authenticator(ctx, cfg)
        mock_auth.configure_curve_callback.assert_called_once()
        call_kwargs = mock_auth.configure_curve_callback.call_args
        provider = call_kwargs[1]["credentials_provider"]
        assert provider._authorized_keys == {"N1.Actor1": "a" * 40}
        mock_load_keys.assert_called_once_with(cfg)

    @patch("pyleco.core.zap.load_authorized_keys", return_value={})
    @patch("pyleco.core.zap.ThreadAuthenticator")
    def test_no_keys_raises_value_error(
        self, mock_thread_auth_cls: MagicMock, mock_load_keys: MagicMock
    ) -> None:
        mock_auth = MagicMock()
        mock_thread_auth_cls.return_value = mock_auth
        ctx = MagicMock()
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp)
        with pytest.raises(ValueError, match="authorized_keys"):
            start_authenticator(ctx, cfg)

    @patch("pyleco.core.zap.load_authorized_keys", return_value={})
    @patch("pyleco.core.zap.ThreadAuthenticator")
    @patch("pyleco.core.zap.CURVE_ALLOW_ANY", "*")
    def test_full_security_config(
        self, mock_thread_auth_cls: MagicMock, mock_load_keys: MagicMock
    ) -> None:
        mock_auth = MagicMock()
        mock_thread_auth_cls.return_value = mock_auth
        ctx = MagicMock()
        skp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        ckp = KeyPair(public_key="c" * 40, secret_key="d" * 40)
        cfg = FullSecurityConfig(
            server_key_pair=skp,
            client_key_pair=ckp,
            server_public_key="e" * 40,
            curve_any_authenticated=True,
        )
        result = start_authenticator(ctx, cfg)
        mock_thread_auth_cls.assert_called_once_with(ctx)
        mock_auth.start.assert_called_once()
        assert result is mock_auth
        mock_load_keys.assert_not_called()


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
