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

import socket
import threading
from time import sleep
from typing import Any

import pytest
import zmq

from pyleco.coordinators.coordinator import Coordinator
from pyleco.core.security import (
    ServerSecurityConfig,
    ClientSecurityConfig,
    FullSecurityConfig,
    generate_key_pair,
)
from pyleco.utils.communicator import Communicator


TIMEOUT = 3


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _close_com(com: Communicator) -> None:
    if hasattr(com, "socket") and not com.socket.closed:
        com.socket.close(linger=0)


def start_coordinator(
    namespace: str,
    port: int,
    security_config: ServerSecurityConfig | FullSecurityConfig,
    stop_event: threading.Event,
    coordinators: list[str] | None = None,
    **kwargs: Any,
):
    with Coordinator(
        namespace=namespace, port=port, security_config=security_config, **kwargs
    ) as coordinator:
        coordinator.routing(coordinators=coordinators, stop_event=stop_event)


@pytest.fixture
def coordinator_keys():
    server_keys = generate_key_pair()
    client_keys = generate_key_pair()
    return server_keys, client_keys


@pytest.fixture
def curve_coordinator(coordinator_keys):
    server_keys, client_keys = coordinator_keys
    server_config = ServerSecurityConfig(
        server_key_pair=server_keys,
        curve_any_authenticated=True,
    )
    port = _find_free_port()
    stop_event = threading.Event()
    thread = threading.Thread(
        target=start_coordinator,
        kwargs=dict(
            namespace="CURVE_N1",
            port=port,
            security_config=server_config,
            stop_event=stop_event,
            host="localhost",
        ),
    )
    thread.daemon = True
    thread.start()
    sleep(1)
    yield server_keys, client_keys, port
    stop_event.set()
    thread.join(timeout=3)


class TestCoordinatorCurveAnyAuthenticated:
    def test_curve_client_can_sign_in(self, curve_coordinator):
        server_keys, client_keys, port = curve_coordinator
        client_config = ClientSecurityConfig(
            client_key_pair=client_keys,
            server_public_key=server_keys.public_key,
        )
        com = Communicator(
            name="TestClient",
            host="localhost",
            port=port,
            timeout=TIMEOUT,
            security_config=client_config,
        )
        try:
            com.open()
            com.sign_in()
            assert com.namespace is not None
            result = com.ask_rpc(receiver="CURVE_N1.COORDINATOR", method="send_local_components")
            assert isinstance(result, list)
        finally:
            com.close()

    def test_none_client_rejected_by_curve_coordinator(self, curve_coordinator):
        _, _, port = curve_coordinator
        com = Communicator(
            name="NoneClient",
            host="localhost",
            port=port,
            timeout=0.3,
            security_config=None,
        )
        try:
            com.open()
            with pytest.raises(ConnectionRefusedError):
                com.sign_in()
            assert com.namespace is None
        finally:
            _close_com(com)

    def test_wrong_server_key_client_rejected(self, curve_coordinator):
        _, client_keys, port = curve_coordinator
        wrong_server_keys = generate_key_pair()
        bad_config = ClientSecurityConfig(
            client_key_pair=client_keys,
            server_public_key=wrong_server_keys.public_key,
        )
        com = Communicator(
            name="BadKeyClient",
            host="localhost",
            port=port,
            timeout=0.3,
            security_config=bad_config,
        )
        try:
            com.open()
            with pytest.raises(ConnectionRefusedError):
                com.sign_in()
            assert com.namespace is None
        finally:
            _close_com(com)


class TestCoordinatorCurveWithAuthorizedKeys:
    def test_authorized_client_can_sign_in(self, coordinator_keys, tmp_path):
        server_keys, client_keys = coordinator_keys

        key_dir = tmp_path / "authorized"
        key_dir.mkdir()
        (key_dir / "TestClient").write_text(client_keys.public_key)

        server_config = ServerSecurityConfig(
            server_key_pair=server_keys,
            authorized_keys_dir=str(key_dir),
        )
        port = _find_free_port()
        stop_event = threading.Event()
        thread = threading.Thread(
            target=start_coordinator,
            kwargs=dict(
                namespace="AUTH_N1",
                port=port,
                security_config=server_config,
                stop_event=stop_event,
                host="localhost",
            ),
        )
        thread.daemon = True
        thread.start()
        sleep(1)
        try:
            client_config = ClientSecurityConfig(
                client_key_pair=client_keys,
                server_public_key=server_keys.public_key,
            )
            com = Communicator(
                name="TestClient",
                host="localhost",
                port=port,
                timeout=TIMEOUT,
                security_config=client_config,
            )
            try:
                com.open()
                com.sign_in()
                assert com.namespace is not None
            finally:
                com.close()
        finally:
            stop_event.set()
            thread.join(timeout=3)

    def test_unauthorized_client_rejected(self, coordinator_keys, tmp_path):
        server_keys, client_keys = coordinator_keys

        other_client_keys = generate_key_pair()

        key_dir = tmp_path / "authorized2"
        key_dir.mkdir()
        (key_dir / "AuthorizedClient").write_text(other_client_keys.public_key)

        server_config = ServerSecurityConfig(
            server_key_pair=server_keys,
            authorized_keys_dir=str(key_dir),
        )
        port = _find_free_port()
        stop_event = threading.Event()
        thread = threading.Thread(
            target=start_coordinator,
            kwargs=dict(
                namespace="AUTH_N2",
                port=port,
                security_config=server_config,
                stop_event=stop_event,
                host="localhost",
            ),
        )
        thread.daemon = True
        thread.start()
        sleep(1)
        try:
            client_config = ClientSecurityConfig(
                client_key_pair=client_keys,
                server_public_key=server_keys.public_key,
            )
            com = Communicator(
                name="UnauthorizedClient",
                host="localhost",
                port=port,
                timeout=0.3,
                security_config=client_config,
            )
            try:
                com.open()
                with pytest.raises(ConnectionRefusedError):
                    com.sign_in()
                assert com.namespace is None
            finally:
                _close_com(com)
        finally:
            stop_event.set()
            thread.join(timeout=3)


class TestProxyServerCurve:
    def test_curve_proxy_relays_data(self):
        from pyleco.coordinators.proxy_server import start_proxy

        proxy_keys = generate_key_pair()
        publisher_keys = generate_key_pair()
        subscriber_keys = generate_key_pair()

        proxy_config = ServerSecurityConfig(
            server_key_pair=proxy_keys,
            curve_any_authenticated=True,
        )

        context = zmq.Context()
        try:
            start_proxy(
                context=context,
                security_config=proxy_config,
                offset=50,
            )
            sleep(0.5)

            from pyleco.core import PROXY_RECEIVING_PORT
            from pyleco.core.curve import configure_curve_client
            from pyleco.utils.data_publisher import DataPublisher

            data_port = PROXY_RECEIVING_PORT - 2 * 50
            publisher_config = ClientSecurityConfig(
                client_key_pair=publisher_keys,
                data_server_public_key=proxy_keys.public_key,
            )

            pub = DataPublisher(
                full_name="TestPub",
                host="localhost",
                port=data_port,
                context=context,
                security_config=publisher_config,
            )

            sub = context.socket(zmq.SUB)
            configure_curve_client(sub, subscriber_keys, proxy_keys.public_key)
            sub.connect(f"tcp://localhost:{data_port - 1}")
            sub.subscribe(b"")

            sleep(0.5)
            pub.send_data(data={"key": "value"}, topic="test_topic")
            sleep(0.2)

            poller = zmq.Poller()
            poller.register(sub, zmq.POLLIN)
            socks = dict(poller.poll(2000))
            assert sub in socks, "Subscriber should receive data from CURVE-secured proxy"

            sub.close(linger=0)
            pub.close()
        finally:
            context.destroy(linger=0)


class TestGenerateKeyPair:
    def test_generates_valid_z85_keys(self):
        key_pair = generate_key_pair()
        assert len(key_pair.public_key) == 40
        assert len(key_pair.secret_key) == 40
        assert key_pair.public_key != key_pair.secret_key

    def test_generates_unique_keys(self):
        keys1 = generate_key_pair()
        keys2 = generate_key_pair()
        assert keys1.public_key != keys2.public_key
