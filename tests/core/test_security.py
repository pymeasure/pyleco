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

import pytest

from pyleco.core.security import (
    KeyPair,
    ServerSecurityConfig,
    ClientSecurityConfig,
    FullSecurityConfig,
    SecurityConfig,
    generate_key_pair,
    load_authorized_keys,
    load_security_config,
)


class TestKeyPair:
    def test_construction(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        assert kp.public_key == "a" * 40
        assert kp.secret_key == "b" * 40


class TestServerSecurityConfig:
    def test_construction(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp)
        assert cfg.server_key_pair is kp
        assert cfg.authorized_keys_dir is None
        assert cfg.authorized_keys is None
        assert cfg.curve_any_authenticated is False

    def test_with_authorized_keys(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ServerSecurityConfig(
            server_key_pair=kp,
            authorized_keys={"N1.Actor1": "c" * 40},
            curve_any_authenticated=True,
        )
        assert cfg.authorized_keys == {"N1.Actor1": "c" * 40}
        assert cfg.curve_any_authenticated is True


class TestClientSecurityConfig:
    def test_construction(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ClientSecurityConfig(
            client_key_pair=kp,
            server_public_key="c" * 40,
        )
        assert cfg.client_key_pair is kp
        assert cfg.server_public_key == "c" * 40
        assert cfg.data_server_public_key is None

    def test_with_data_server_public_key(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ClientSecurityConfig(
            client_key_pair=kp,
            server_public_key="c" * 40,
            data_server_public_key="d" * 40,
        )
        assert cfg.data_server_public_key == "d" * 40

    def test_without_server_public_key(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg = ClientSecurityConfig(
            client_key_pair=kp,
            data_server_public_key="d" * 40,
        )
        assert cfg.server_public_key is None
        assert cfg.data_server_public_key == "d" * 40


class TestFullSecurityConfig:
    def test_construction(self) -> None:
        skp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        ckp = KeyPair(public_key="c" * 40, secret_key="d" * 40)
        cfg = FullSecurityConfig(
            server_key_pair=skp,
            client_key_pair=ckp,
            server_public_key="e" * 40,
        )
        assert cfg.server_key_pair is skp
        assert cfg.client_key_pair is ckp
        assert cfg.server_public_key == "e" * 40
        assert isinstance(cfg, ServerSecurityConfig)
        assert isinstance(cfg, ClientSecurityConfig)

    def test_isinstance_checks(self) -> None:
        skp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        ckp = KeyPair(public_key="c" * 40, secret_key="d" * 40)
        cfg = FullSecurityConfig(
            server_key_pair=skp,
            client_key_pair=ckp,
            server_public_key="e" * 40,
        )
        assert isinstance(cfg, (ServerSecurityConfig, FullSecurityConfig))
        assert isinstance(cfg, (ClientSecurityConfig, FullSecurityConfig))


class TestSecurityConfigTypeAlias:
    def test_server_config_is_security_config(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg: SecurityConfig = ServerSecurityConfig(server_key_pair=kp)
        assert isinstance(cfg, ServerSecurityConfig)

    def test_client_config_is_security_config(self) -> None:
        kp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        cfg: SecurityConfig = ClientSecurityConfig(client_key_pair=kp, server_public_key="c" * 40)
        assert isinstance(cfg, ClientSecurityConfig)

    def test_full_config_is_security_config(self) -> None:
        skp = KeyPair(public_key="a" * 40, secret_key="b" * 40)
        ckp = KeyPair(public_key="c" * 40, secret_key="d" * 40)
        cfg: SecurityConfig = FullSecurityConfig(
            server_key_pair=skp,
            client_key_pair=ckp,
            server_public_key="e" * 40,
        )
        assert isinstance(cfg, FullSecurityConfig)


class TestGenerateKeyPair:
    def test_returns_keypair(self) -> None:
        kp = generate_key_pair()
        assert isinstance(kp, KeyPair)
        assert len(kp.public_key) == 40
        assert len(kp.secret_key) == 40

    def test_import_error_without_zmq(self) -> None:
        import pyleco.core.security as sec

        sec.__dict__.get("zmq")
        import builtins

        orig_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "zmq":
                raise ImportError("no zmq")
            return orig_import(name, *args, **kwargs)

        builtins.__import__ = fake_import
        try:
            with pytest.raises(ImportError, match="zmq is required"):
                generate_key_pair()
        finally:
            builtins.__import__ = orig_import


class TestLoadAuthorizedKeys:
    def test_from_directory(self, tmp_path: pytest.TempPath) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1.public").write_text("a" * 40)
        (key_dir / "N1.Actor2.public").write_text("b" * 40)
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys_dir=str(key_dir))
        result = load_authorized_keys(cfg)
        assert result == {"N1.Actor1": "a" * 40, "N1.Actor2": "b" * 40}

    def test_from_inline_dict(self) -> None:
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys={"N1.Actor1": "a" * 40})
        result = load_authorized_keys(cfg)
        assert result == {"N1.Actor1": "a" * 40}

    def test_merge_both_sources(self, tmp_path: pytest.TempPath) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1.public").write_text("a" * 40)
        (key_dir / "N1.Actor2.public").write_text("b" * 40)
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(
            server_key_pair=kp,
            authorized_keys_dir=str(key_dir),
            authorized_keys={"N1.Actor2": "c" * 40, "N1.Actor3": "d" * 40},
        )
        result = load_authorized_keys(cfg)
        assert result == {
            "N1.Actor1": "a" * 40,
            "N1.Actor2": "c" * 40,
            "N1.Actor3": "d" * 40,
        }

    def test_no_keys_dir(self) -> None:
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys_dir="/nonexistent/path")
        assert load_authorized_keys(cfg) == {}

    def test_skips_hidden_files(self, tmp_path: pytest.TempPath) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1.public").write_text("a" * 40)
        (key_dir / ".hidden").write_text("x" * 40)
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys_dir=str(key_dir))
        result = load_authorized_keys(cfg)
        assert result == {"N1.Actor1": "a" * 40}

    def test_file_without_extension(self, tmp_path: pytest.TempPath) -> None:
        key_dir = tmp_path / "keys"
        key_dir.mkdir()
        (key_dir / "N1.Actor1").write_text("a" * 40)
        kp = KeyPair(public_key="s" * 40, secret_key="t" * 40)
        cfg = ServerSecurityConfig(server_key_pair=kp, authorized_keys_dir=str(key_dir))
        result = load_authorized_keys(cfg)
        assert result == {"N1.Actor1": "a" * 40}


class TestLoadSecurityConfig:
    def test_no_args_returns_none(self) -> None:
        cfg = load_security_config()
        assert cfg is None

    def test_cli_args_server_keys(self) -> None:
        cfg = load_security_config(
            cli_args={
                "server_public_key": "a" * 40,
                "server_secret_key": "b" * 40,
            }
        )
        assert isinstance(cfg, ServerSecurityConfig)
        assert cfg.server_key_pair is not None
        assert cfg.server_key_pair.public_key == "a" * 40
        assert cfg.server_key_pair.secret_key == "b" * 40

    def test_cli_args_client_keys(self) -> None:
        cfg = load_security_config(
            cli_args={
                "client_public_key": "a" * 40,
                "client_secret_key": "b" * 40,
                "server_public_key": "c" * 40,
            }
        )
        assert isinstance(cfg, ClientSecurityConfig)
        assert cfg.client_key_pair is not None
        assert cfg.client_key_pair.public_key == "a" * 40
        assert cfg.server_public_key == "c" * 40

    def test_cli_args_client_keys_without_server_public_key(self) -> None:
        cfg = load_security_config(
            cli_args={
                "client_public_key": "a" * 40,
                "client_secret_key": "b" * 40,
                "data_server_public_key": "d" * 40,
            }
        )
        assert isinstance(cfg, ClientSecurityConfig)
        assert cfg.client_key_pair is not None
        assert cfg.server_public_key is None
        assert cfg.data_server_public_key == "d" * 40

    def test_cli_args_both_keys(self) -> None:
        cfg = load_security_config(
            cli_args={
                "server_public_key": "a" * 40,
                "server_secret_key": "b" * 40,
                "client_public_key": "c" * 40,
                "client_secret_key": "d" * 40,
            }
        )
        assert isinstance(cfg, FullSecurityConfig)
        assert cfg.server_key_pair is not None
        assert cfg.client_key_pair is not None
        assert cfg.server_public_key == "a" * 40

    def test_toml_file(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text(
            "[security]\n"
            'server_public_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
            'server_secret_key = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
        )
        cfg = load_security_config(config_path=str(toml_file))
        assert isinstance(cfg, ServerSecurityConfig)
        assert cfg.server_key_pair is not None
        assert cfg.server_key_pair.public_key == "a" * 40
        assert cfg.server_key_pair.secret_key == "b" * 40

    def test_toml_with_authorized_keys(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text(
            "[security]\n"
            'server_public_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
            'server_secret_key = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
            "[security.authorized_keys]\n"
            '"N1.Actor1" = "cccccccccccccccccccccccccccccccccccccccc"\n'
        )
        cfg = load_security_config(config_path=str(toml_file))
        assert isinstance(cfg, ServerSecurityConfig)
        assert cfg.authorized_keys == {"N1.Actor1": "c" * 40}

    def test_cli_none_values_do_not_override(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text('[security]\nauthorized_keys_dir = "/some/path"\n')
        cfg = load_security_config(
            config_path=str(toml_file),
            cli_args={"authorized_keys_dir": None},
        )
        assert cfg is None

    def test_toml_with_data_server_public_key(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text(
            "[security]\n"
            'client_public_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
            'client_secret_key = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
            'server_public_key = "cccccccccccccccccccccccccccccccccccccccc"\n'
            'data_server_public_key = "dddddddddddddddddddddddddddddddddddddddd"\n'
        )
        cfg = load_security_config(config_path=str(toml_file))
        assert isinstance(cfg, ClientSecurityConfig)
        assert cfg.data_server_public_key == "d" * 40

    def test_toml_with_curve_any_authenticated(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "pyleco.toml"
        toml_file.write_text(
            "[security]\n"
            'server_public_key = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n'
            'server_secret_key = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"\n'
            "curve_any_authenticated = true\n"
        )
        cfg = load_security_config(config_path=str(toml_file))
        assert isinstance(cfg, ServerSecurityConfig)
        assert cfg.curve_any_authenticated is True
