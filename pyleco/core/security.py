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

from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "ServerSecurityConfig",
    "ClientSecurityConfig",
    "FullSecurityConfig",
    "KeyPair",
    "SecurityConfig",
    "generate_key_pair",
    "load_authorized_keys",
    "load_security_config",
]


@dataclass
class KeyPair:
    public_key: str
    secret_key: str


@dataclass(kw_only=True)
class ServerSecurityConfig:
    server_key_pair: KeyPair
    authorized_keys_dir: str | None = None
    authorized_keys: dict[str, str] | None = None
    curve_any_authenticated: bool = False


@dataclass(kw_only=True)
class ClientSecurityConfig:
    client_key_pair: KeyPair
    server_public_key: str | None = None
    data_server_public_key: str | None = None


@dataclass(kw_only=True)
class FullSecurityConfig(ServerSecurityConfig, ClientSecurityConfig):
    server_public_key: str


SecurityConfig = ServerSecurityConfig | ClientSecurityConfig | FullSecurityConfig


def generate_key_pair() -> KeyPair:
    import zmq

    public_key, secret_key = zmq.curve_keypair()
    return KeyPair(public_key=public_key.decode(), secret_key=secret_key.decode())


def load_authorized_keys(
    security_config: ServerSecurityConfig | FullSecurityConfig,
) -> dict[str, str]:
    keys: dict[str, str] = {}
    if security_config.authorized_keys_dir is not None:
        key_dir = Path(security_config.authorized_keys_dir)
        if key_dir.is_dir():
            for path in sorted(key_dir.iterdir()):
                if path.is_file() and not path.name.startswith("."):
                    name = path.stem if path.suffix == ".public" else path.name
                    content = path.read_text().strip()
                    if content:
                        keys[name] = content
    if security_config.authorized_keys is not None:
        keys.update(security_config.authorized_keys)
    return keys


def load_security_config(
    config_path: str | None = None,
    cli_args: dict | None = None,
) -> SecurityConfig | None:
    config_dict: dict = {}
    if config_path is not None:
        from pyleco.core.config import _load_toml

        data = _load_toml(config_path)
        config_dict = data.get("security", {})

    server_key_pair: KeyPair | None = None
    client_key_pair: KeyPair | None = None
    server_public_key: str | None = None
    data_server_public_key: str | None = None
    authorized_keys_dir: str | None = None
    authorized_keys: dict[str, str] | None = None
    curve_any_authenticated: bool = False

    if "server_secret_key" in config_dict and "server_public_key" in config_dict:
        server_key_pair = KeyPair(
            public_key=config_dict["server_public_key"],
            secret_key=config_dict["server_secret_key"],
        )
    if "client_secret_key" in config_dict and "client_public_key" in config_dict:
        client_key_pair = KeyPair(
            public_key=config_dict["client_public_key"],
            secret_key=config_dict["client_secret_key"],
        )
    if "server_public_key" in config_dict and server_key_pair is None:
        server_public_key = config_dict["server_public_key"]
    if "data_server_public_key" in config_dict:
        data_server_public_key = config_dict["data_server_public_key"]
    if "authorized_keys_dir" in config_dict:
        authorized_keys_dir = config_dict["authorized_keys_dir"]
    if "authorized_keys" in config_dict:
        authorized_keys = dict(config_dict["authorized_keys"])
    if "curve_any_authenticated" in config_dict:
        curve_any_authenticated = config_dict["curve_any_authenticated"]

    cli_server_secret = None
    cli_server_public = None
    cli_client_secret = None
    cli_client_public = None

    if cli_args is not None:
        for key, value in cli_args.items():
            if value is not None:
                if key == "server_secret_key":
                    cli_server_secret = value
                elif key == "server_public_key":
                    cli_server_public = value
                elif key == "client_secret_key":
                    cli_client_secret = value
                elif key == "client_public_key":
                    cli_client_public = value
                elif key == "data_server_public_key":
                    data_server_public_key = value
                elif key == "authorized_keys_dir":
                    authorized_keys_dir = value
                elif key == "curve_any_authenticated":
                    curve_any_authenticated = value

    if cli_server_secret is not None and cli_server_public is not None:
        server_key_pair = KeyPair(
            public_key=cli_server_public,
            secret_key=cli_server_secret,
        )
    elif cli_server_secret is not None:
        if server_key_pair is not None and server_key_pair.public_key:
            server_key_pair = KeyPair(
                public_key=server_key_pair.public_key,
                secret_key=cli_server_secret,
            )
    elif cli_server_public is not None:
        if server_key_pair is not None and server_key_pair.secret_key:
            server_key_pair = KeyPair(
                public_key=cli_server_public,
                secret_key=server_key_pair.secret_key,
            )

    if cli_server_public is not None:
        server_public_key = cli_server_public

    if cli_client_secret is not None and cli_client_public is not None:
        client_key_pair = KeyPair(
            public_key=cli_client_public,
            secret_key=cli_client_secret,
        )
    elif cli_client_secret is not None:
        if client_key_pair is not None and client_key_pair.public_key:
            client_key_pair = KeyPair(
                public_key=client_key_pair.public_key,
                secret_key=cli_client_secret,
            )
    elif cli_client_public is not None:
        if client_key_pair is not None and client_key_pair.secret_key:
            client_key_pair = KeyPair(
                public_key=cli_client_public,
                secret_key=client_key_pair.secret_key,
            )

    has_server = server_key_pair is not None
    has_client = client_key_pair is not None
    has_server_public_key = server_public_key is not None

    if has_server and has_client and has_server_public_key:
        assert server_key_pair is not None
        assert client_key_pair is not None
        assert server_public_key is not None
        return FullSecurityConfig(
            server_key_pair=server_key_pair,
            client_key_pair=client_key_pair,
            server_public_key=server_public_key,
            data_server_public_key=data_server_public_key,
            authorized_keys_dir=authorized_keys_dir,
            authorized_keys=authorized_keys,
            curve_any_authenticated=curve_any_authenticated,
        )
    elif has_server:
        assert server_key_pair is not None
        return ServerSecurityConfig(
            server_key_pair=server_key_pair,
            authorized_keys_dir=authorized_keys_dir,
            authorized_keys=authorized_keys,
            curve_any_authenticated=curve_any_authenticated,
        )
    elif has_client:
        assert client_key_pair is not None
        return ClientSecurityConfig(
            client_key_pair=client_key_pair,
            server_public_key=server_public_key,
            data_server_public_key=data_server_public_key,
        )
    else:
        return None
