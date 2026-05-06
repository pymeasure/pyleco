from __future__ import annotations

import warnings
from unittest.mock import MagicMock

from pyleco.core.curve import (
    configure_curve_client,
    configure_curve_server,
    warn_insecure_mode,
)
from pyleco.core.security import KeyPair

FAKE_PUBLIC = "a" * 40
FAKE_SECRET = "b" * 40
FAKE_SERVER_PUBLIC = "c" * 40


class TestConfigureCurveServer:
    def test_sets_socket_options(self) -> None:
        socket = MagicMock()
        kp = KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET)
        configure_curve_server(socket, kp)
        assert socket.curve_server is True
        assert socket.curve_secretkey == FAKE_SECRET.encode()

    def test_curve_server_true(self) -> None:
        socket = MagicMock()
        kp = KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET)
        configure_curve_server(socket, kp)
        assert socket.curve_server is True

    def test_secret_key_encoded(self) -> None:
        socket = MagicMock()
        kp = KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET)
        configure_curve_server(socket, kp)
        assert socket.curve_secretkey == FAKE_SECRET.encode()


class TestConfigureCurveClient:
    def test_sets_socket_options(self) -> None:
        socket = MagicMock()
        kp = KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET)
        configure_curve_client(socket, kp, FAKE_SERVER_PUBLIC)
        assert socket.curve_serverkey == FAKE_SERVER_PUBLIC.encode()
        assert socket.curve_publickey == FAKE_PUBLIC.encode()
        assert socket.curve_secretkey == FAKE_SECRET.encode()


class TestWarnInsecureMode:
    def test_none_address_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode(None)
            assert len(w) == 0

    def test_localhost_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("localhost:12300")
            assert len(w) == 0

    def test_127_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("127.0.0.1:12300")
            assert len(w) == 0

    def test_ipv6_loopback_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("::1:12300")
            assert len(w) == 0

    def test_ipv6_bracketed_loopback_no_warning(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("[::1]:12300")
            assert len(w) == 0

    def test_non_loopback_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("192.168.1.1:12300")
            assert len(w) == 1
            assert issubclass(w[0].category, UserWarning)
            assert "insecure" in str(w[0].message)

    def test_no_port_warns(self) -> None:
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            warn_insecure_mode("10.0.0.1")
            assert len(w) == 1
