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

import logging

import zmq
from zmq.auth import CURVE_ALLOW_ANY
from zmq.auth.thread import ThreadAuthenticator

from pyleco.core.security import ServerSecurityConfig, FullSecurityConfig, load_authorized_keys

__all__ = [
    "start_authenticator",
    "stop_authenticator",
]

log = logging.getLogger(__name__)


class _CredentialsProvider:
    def __init__(self, authorized_keys: dict[str, str] | None = None, allow_any: bool = False):
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


def start_authenticator(
    context: zmq.Context, security_config: ServerSecurityConfig | FullSecurityConfig
) -> ThreadAuthenticator:

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


def stop_authenticator(authenticator: ThreadAuthenticator) -> None:
    try:
        authenticator.stop()
    except Exception:
        log.exception("Error stopping ZAP authenticator")
