from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional

__all__ = [
    "SecurityMode",
    "KeyPair",
    "SecurityConfig",
    "generate_key_pair",
    "load_authorized_keys",
    "load_security_config",
]


class SecurityMode(Enum):
    NONE = "NONE"
    CURVE = "CURVE"


@dataclass
class KeyPair:
    public_key: str
    secret_key: str


@dataclass
class SecurityConfig:
    mode: SecurityMode = SecurityMode.NONE
    server_key_pair: Optional[KeyPair] = None
    client_key_pair: Optional[KeyPair] = None
    server_public_key: Optional[str] = None
    data_server_public_key: Optional[str] = None
    authorized_keys_dir: Optional[str] = None
    authorized_keys: Optional[Dict[str, str]] = None
    curve_any_authenticated: bool = False

    def validate(self) -> None:
        if self.mode == SecurityMode.NONE:
            return
        if self.mode == SecurityMode.CURVE:
            has_server_keys = self.server_key_pair is not None
            has_client_keys = (
                self.client_key_pair is not None and self.server_public_key is not None
            )
            if not has_server_keys and not has_client_keys:
                raise ValueError(
                    "CURVE mode requires either server_key_pair (for servers) "
                    "or client_key_pair + server_public_key (for clients)"
                )
            if self.client_key_pair is not None and self.server_public_key is None:
                raise ValueError(
                    "CURVE mode with client_key_pair also requires server_public_key"
                )


def generate_key_pair() -> KeyPair:
    try:
        import zmq
    except ImportError:
        raise ImportError(
            "zmq is required to generate CURVE key pairs. "
            "Install pyzmq: pip install pyzmq"
        )
    public_key, secret_key = zmq.curve_keypair()
    return KeyPair(public_key=public_key.decode(), secret_key=secret_key.decode())


def load_authorized_keys(security_config: SecurityConfig) -> Dict[str, str]:
    keys: Dict[str, str] = {}
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
    config_path: Optional[str] = None,
    cli_args: Optional[dict] = None,
) -> SecurityConfig:
    config_dict: dict = {}
    if config_path is not None:
        from pyleco.core.config import _load_toml
        data = _load_toml(config_path)
        config_dict = data.get("security", {})
    kwargs: dict = {}
    if "mode" in config_dict:
        kwargs["mode"] = SecurityMode(config_dict["mode"])
    if "server_secret_key" in config_dict and "server_public_key" in config_dict:
        kwargs["server_key_pair"] = KeyPair(
            public_key=config_dict["server_public_key"],
            secret_key=config_dict["server_secret_key"],
        )
    if "client_secret_key" in config_dict and "client_public_key" in config_dict:
        kwargs["client_key_pair"] = KeyPair(
            public_key=config_dict["client_public_key"],
            secret_key=config_dict["client_secret_key"],
        )
    if "server_public_key" in config_dict and "server_key_pair" not in kwargs:
        kwargs["server_public_key"] = config_dict["server_public_key"]
    if "data_server_public_key" in config_dict:
        kwargs["data_server_public_key"] = config_dict["data_server_public_key"]
    if "authorized_keys_dir" in config_dict:
        kwargs["authorized_keys_dir"] = config_dict["authorized_keys_dir"]
    if "authorized_keys" in config_dict:
        kwargs["authorized_keys"] = dict(config_dict["authorized_keys"])
    if "curve_any_authenticated" in config_dict:
        kwargs["curve_any_authenticated"] = config_dict["curve_any_authenticated"]
    cli_server_secret = None
    cli_server_public = None
    cli_client_secret = None
    cli_client_public = None
    if cli_args is not None:
        for key, value in cli_args.items():
            if value is not None:
                if key == "mode":
                    kwargs["mode"] = SecurityMode(value)
                elif key == "server_secret_key":
                    cli_server_secret = value
                elif key == "server_public_key":
                    cli_server_public = value
                elif key == "client_secret_key":
                    cli_client_secret = value
                elif key == "client_public_key":
                    cli_client_public = value
                else:
                    kwargs[key] = value
    if cli_server_secret is not None and cli_server_public is not None:
        kwargs["server_key_pair"] = KeyPair(
            public_key=cli_server_public, secret_key=cli_server_secret,
        )
    elif cli_server_secret is not None:
        existing = kwargs.get("server_key_pair")
        if existing is not None and existing.public_key:
            kwargs["server_key_pair"] = KeyPair(
                public_key=existing.public_key, secret_key=cli_server_secret,
            )
    elif cli_server_public is not None:
        existing = kwargs.get("server_key_pair")
        if existing is not None and existing.secret_key:
            kwargs["server_key_pair"] = KeyPair(
                public_key=cli_server_public, secret_key=existing.secret_key,
            )
    if cli_server_public is not None:
        kwargs["server_public_key"] = cli_server_public
    if cli_client_secret is not None and cli_client_public is not None:
        kwargs["client_key_pair"] = KeyPair(
            public_key=cli_client_public, secret_key=cli_client_secret,
        )
    elif cli_client_secret is not None:
        existing = kwargs.get("client_key_pair")
        if existing is not None and existing.public_key:
            kwargs["client_key_pair"] = KeyPair(
                public_key=existing.public_key, secret_key=cli_client_secret,
            )
    elif cli_client_public is not None:
        existing = kwargs.get("client_key_pair")
        if existing is not None and existing.secret_key:
            kwargs["client_key_pair"] = KeyPair(
                public_key=cli_client_public, secret_key=existing.secret_key,
            )
    return SecurityConfig(**kwargs)
