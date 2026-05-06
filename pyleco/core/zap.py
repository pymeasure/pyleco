from __future__ import annotations

import logging

from typing import Dict, Optional

from pyleco.core.security import SecurityConfig, SecurityMode, load_authorized_keys

__all__ = [
    "start_authenticator",
    "stop_authenticator",
]

log = logging.getLogger(__name__)


class _CredentialsProvider:
    def __init__(self, authorized_keys: Optional[Dict[str, str]] = None, allow_any: bool = False):
        self._authorized_keys = authorized_keys
        self._authorized_key_values = set(authorized_keys.values()) if authorized_keys else None
        self._allow_any = allow_any

    def callback(self, domain: str, key: bytes) -> bool:
        if self._allow_any:
            return True
        if self._authorized_key_values is not None:
            try:
                decoded = key.decode("utf-8")
            except UnicodeDecodeError:
                return False
            return decoded in self._authorized_key_values
        return False


def start_authenticator(context, security_config: SecurityConfig):
    from zmq.auth import CURVE_ALLOW_ANY
    from zmq.auth.thread import ThreadAuthenticator

    if security_config.mode != SecurityMode.CURVE:
        raise ValueError("start_authenticator requires SecurityMode.CURVE")

    authenticator = ThreadAuthenticator(context)
    authenticator.start()
    if security_config.curve_any_authenticated:
        authenticator.configure_curve(domain="*", location=CURVE_ALLOW_ANY)
    else:
        authorized_keys = load_authorized_keys(security_config)
        if authorized_keys:
            provider = _CredentialsProvider(authorized_keys=authorized_keys)
            authenticator.configure_curve_callback(domain="*", credentials_provider=provider)
        else:
            raise ValueError(
                "CURVE mode requires either authorized_keys_dir, authorized_keys, "
                "or curve_any_authenticated=True. No authorized keys were found."
            )
    return authenticator


def stop_authenticator(authenticator) -> None:
    try:
        authenticator.stop()
    except Exception:
        log.exception("Error stopping ZAP authenticator")
