from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from pyleco.core.security import KeyPair, SecurityConfig, SecurityMode


FAKE_PUBLIC = "a" * 40
FAKE_SECRET = "b" * 40
FAKE_SERVER_PUBLIC = "c" * 40
FAKE_DATA_PUBLIC = "d" * 40


def _make_client_config() -> SecurityConfig:
    return SecurityConfig(
        mode=SecurityMode.CURVE,
        client_key_pair=KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET),
        server_public_key=FAKE_SERVER_PUBLIC,
        data_server_public_key=FAKE_DATA_PUBLIC,
    )


def _make_server_config() -> SecurityConfig:
    return SecurityConfig(
        mode=SecurityMode.CURVE,
        server_key_pair=KeyPair(public_key=FAKE_PUBLIC, secret_key=FAKE_SECRET),
    )


_zmq_modules = [
    "zmq",
    "zmq.backend",
    "zmq.backend.cython",
    "zmq.backend.cython._zmq",
    "zmq.sugar",
    "zmq.sugar.constants",
    "zmq.auth",
    "zmq.auth.thread",
]


def _setup_zmq_mock():
    mocks = {}
    for mod_name in _zmq_modules:
        if mod_name not in sys.modules:
            mocks[mod_name] = MagicMock()
            sys.modules[mod_name] = mocks[mod_name]
    return mocks


def _teardown_zmq_mock(mocks):
    for mod_name in mocks:
        if sys.modules.get(mod_name) is mocks[mod_name]:
            del sys.modules[mod_name]


@pytest.fixture(autouse=True)
def mock_zmq():
    mocks = _setup_zmq_mock()
    yield
    _teardown_zmq_mock(mocks)


class TestCommunicatorCurveMode:
    def test_curve_mode_calls_configure_curve_client(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.communicator.configure_curve_client", mock_configure), patch(
            "pyleco.utils.communicator.warn_insecure_mode"
        ):
            from pyleco.utils.communicator import Communicator

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            cfg = _make_client_config()
            com = Communicator(name="test", auto_open=False, security_config=cfg)
            com.open(context=mock_context)
            mock_configure.assert_called_once_with(
                mock_socket, cfg.client_key_pair, cfg.server_public_key
            )

    def test_none_mode_does_not_call_configure_curve_client(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.communicator.configure_curve_client", mock_configure), patch(
            "pyleco.utils.communicator.warn_insecure_mode"
        ):
            from pyleco.utils.communicator import Communicator

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            com = Communicator(name="test", auto_open=False, security_config=None)
            com.open(context=mock_context)
            mock_configure.assert_not_called()


class TestMessageHandlerCurveMode:
    def test_curve_mode_calls_configure_curve_client(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.message_handler.configure_curve_client", mock_configure), patch(
            "pyleco.utils.message_handler.warn_insecure_mode"
        ):
            from pyleco.utils.message_handler import MessageHandler

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            cfg = _make_client_config()
            handler = MessageHandler(name="test", security_config=cfg, context=mock_context)
            mock_configure.assert_called_once_with(
                mock_socket, cfg.client_key_pair, cfg.server_public_key
            )

    def test_none_mode_does_not_call_configure_curve_client(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.message_handler.configure_curve_client", mock_configure), patch(
            "pyleco.utils.message_handler.warn_insecure_mode"
        ):
            from pyleco.utils.message_handler import MessageHandler

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            handler = MessageHandler(name="test", context=mock_context)
            mock_configure.assert_not_called()


class TestDataPublisherCurveMode:
    def test_curve_mode_calls_configure_curve_client_with_data_key(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.data_publisher.configure_curve_client", mock_configure):
            from pyleco.utils.data_publisher import DataPublisher

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            cfg = _make_client_config()
            pub = DataPublisher(full_name="test", security_config=cfg, context=mock_context)
            mock_configure.assert_called_once_with(
                mock_socket, cfg.client_key_pair, cfg.data_server_public_key
            )

    def test_none_mode_does_not_call_configure_curve_client(self) -> None:
        mock_configure = MagicMock()
        with patch("pyleco.utils.data_publisher.configure_curve_client", mock_configure):
            from pyleco.utils.data_publisher import DataPublisher

            mock_context = MagicMock()
            mock_socket = MagicMock()
            mock_context.socket.return_value = mock_socket
            pub = DataPublisher(full_name="test", context=mock_context)
            mock_configure.assert_not_called()


class TestFakeSocketCurveAttributes:
    def test_curve_server(self) -> None:
        from pyleco.core.message import Message

        class FakeSocket:
            def __init__(self):
                self.curve_server = 0
                self.curve_secretkey = b""
                self.curve_publickey = b""
                self.curve_serverkey = b""
                self.closed = False
                self.socket_type = 5
                self._s = []
                self._r = []
                self.addr = None

            def setsockopt(self, option, value):
                if option == 61:
                    self.curve_server = value
                elif option == 63:
                    self.curve_secretkey = value if isinstance(value, bytes) else value.encode()
                elif option == 62:
                    self.curve_publickey = value if isinstance(value, bytes) else value.encode()
                elif option == 64:
                    self.curve_serverkey = value if isinstance(value, bytes) else value.encode()

        sock = FakeSocket()
        sock.curve_server = 1
        assert sock.curve_server == 1
        sock.curve_secretkey = b"secret"
        assert sock.curve_secretkey == b"secret"
        sock.curve_publickey = b"public"
        assert sock.curve_publickey == b"public"
        sock.curve_serverkey = b"server"
        assert sock.curve_serverkey == b"server"
        sock.setsockopt(61, 1)
        assert sock.curve_server == 1
        sock.setsockopt(63, b"secret2")
        assert sock.curve_secretkey == b"secret2"
