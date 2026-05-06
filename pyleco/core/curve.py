from __future__ import annotations

import warnings
from typing import Optional

from pyleco.core.security import KeyPair

__all__ = [
    "configure_curve_server",
    "configure_curve_client",
    "warn_insecure_mode",
]


def configure_curve_server(socket, server_key_pair: KeyPair) -> None:
    socket.curve_server = True
    socket.curve_secretkey = server_key_pair.secret_key.encode()


def configure_curve_client(
    socket, client_key_pair: KeyPair, server_public_key: str
) -> None:
    socket.curve_serverkey = server_public_key.encode()
    socket.curve_publickey = client_key_pair.public_key.encode()
    socket.curve_secretkey = client_key_pair.secret_key.encode()


def warn_insecure_mode(address: Optional[str] = None, stacklevel: int = 3) -> None:
    if address is None:
        return
    loopback_hosts = {"localhost", "127.0.0.1", "::1"}
    host = address.rsplit(":", 1)[0] if ":" in address else address
    host = host.strip("[]")
    if host not in loopback_hosts:
        warnings.warn(
            "NONE security mode on non-loopback interface is insecure",
            UserWarning,
            stacklevel=stacklevel,
        )
