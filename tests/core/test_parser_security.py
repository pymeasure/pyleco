from __future__ import annotations

import pytest

from pyleco.core.security import SecurityConfig, SecurityMode
from pyleco.utils.parser import (
    build_security_config_from_kwargs,
    parse_command_line_parameters,
    parser,
)


class TestSecurityModeArg:
    def test_security_mode_curve(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--security-mode", "CURVE"],
        )
        assert kwargs.get("security_mode") == "CURVE"

    def test_security_mode_none(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--security-mode", "NONE"],
        )
        assert kwargs.get("security_mode") == "NONE"

    def test_security_mode_default(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=[],
        )
        assert "security_mode" not in kwargs

    def test_server_secret_key(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--server-secret-key", "abc"],
        )
        assert kwargs.get("server_secret_key") == "abc"

    def test_server_public_key(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--server-public-key", "def"],
        )
        assert kwargs.get("server_public_key") == "def"

    def test_client_secret_key(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--client-secret-key", "ghi"],
        )
        assert kwargs.get("client_secret_key") == "ghi"

    def test_client_public_key(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--client-public-key", "jkl"],
        )
        assert kwargs.get("client_public_key") == "jkl"

    def test_data_server_public_key(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--data-server-public-key", "mno"],
        )
        assert kwargs.get("data_server_public_key") == "mno"

    def test_authorized_keys_dir(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--authorized-keys-dir", "/some/path"],
        )
        assert kwargs.get("authorized_keys_dir") == "/some/path"

    def test_curve_any_authenticated(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--curve-any-authenticated"],
        )
        assert kwargs.get("curve_any_authenticated") is True

    def test_config_path(self) -> None:
        kwargs = parse_command_line_parameters(
            parser=parser,
            arguments=["--config", "/path/to/config.toml"],
        )
        assert kwargs.get("config") == "/path/to/config.toml"


class TestBuildSecurityConfigFromKwargs:
    def test_no_security_args_returns_none_mode(self) -> None:
        kwargs: dict = {"host": "localhost", "name": "test"}
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.mode == SecurityMode.NONE

    def test_extracts_curve_args(self) -> None:
        kwargs: dict = {
            "security_mode": "CURVE",
            "server_public_key": "a" * 40,
            "server_secret_key": "b" * 40,
            "host": "localhost",
        }
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.mode == SecurityMode.CURVE
        assert cfg.server_key_pair is not None
        assert cfg.server_key_pair.public_key == "a" * 40
        assert cfg.server_key_pair.secret_key == "b" * 40

    def test_removes_security_keys_from_kwargs(self) -> None:
        kwargs: dict = {
            "security_mode": "CURVE",
            "server_public_key": "a" * 40,
            "server_secret_key": "b" * 40,
            "host": "localhost",
            "name": "comp",
        }
        build_security_config_from_kwargs(kwargs)
        assert "security_mode" not in kwargs
        assert "server_public_key" not in kwargs
        assert "server_secret_key" not in kwargs
        assert "host" in kwargs
        assert "name" in kwargs

    def test_removes_all_security_kwarg_keys(self) -> None:
        kwargs: dict = {
            "security_mode": "NONE",
            "server_secret_key": None,
            "server_public_key": None,
            "client_secret_key": None,
            "client_public_key": None,
            "data_server_public_key": None,
            "authorized_keys_dir": None,
            "curve_any_authenticated": None,
            "host": "localhost",
        }
        build_security_config_from_kwargs(kwargs)
        assert "security_mode" not in kwargs
        assert "server_secret_key" not in kwargs
        assert "server_public_key" not in kwargs
        assert "client_secret_key" not in kwargs
        assert "client_public_key" not in kwargs
        assert "data_server_public_key" not in kwargs
        assert "authorized_keys_dir" not in kwargs
        assert "curve_any_authenticated" not in kwargs
        assert "host" in kwargs

    def test_removes_config_key(self, tmp_path: pytest.TempPath) -> None:
        toml_file = tmp_path / "test.toml"
        toml_file.write_text('[security]\nmode = "NONE"\n')
        kwargs: dict = {"config": str(toml_file), "host": "localhost"}
        build_security_config_from_kwargs(kwargs)
        assert "config" not in kwargs
        assert "host" in kwargs

    def test_client_keys_extracted(self) -> None:
        kwargs: dict = {
            "security_mode": "CURVE",
            "client_public_key": "a" * 40,
            "client_secret_key": "b" * 40,
            "server_public_key": "c" * 40,
        }
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.client_key_pair is not None
        assert cfg.client_key_pair.public_key == "a" * 40
        assert cfg.server_public_key == "c" * 40

    def test_data_server_public_key_extracted(self) -> None:
        kwargs: dict = {
            "data_server_public_key": "d" * 40,
        }
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.data_server_public_key == "d" * 40

    def test_authorized_keys_dir_extracted(self) -> None:
        kwargs: dict = {
            "authorized_keys_dir": "/keys",
        }
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.authorized_keys_dir == "/keys"

    def test_curve_any_authenticated_extracted(self) -> None:
        kwargs: dict = {
            "curve_any_authenticated": True,
        }
        cfg = build_security_config_from_kwargs(kwargs)
        assert cfg.curve_any_authenticated is True
