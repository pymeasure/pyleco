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

"""
Multi-node Data Coordinator using a Gatherer/Distributor architecture.

The DataCoordinator contains two internally coupled proxy servers:
- Gatherer: collects messages from local publishers
- Distributor: distributes messages to local subscribers

For multi-node deployments, the Distributor connects to remote Gatherers'
XPUB sockets, enabling loop-free cross-node data distribution.

It participates in the control protocol as a Component (via a Listener)
to expose RPC methods for dynamic remote Gatherer connection management.

A single DataCoordinator instance manages one proxy pair (either data or log).
To run both data and log coordinators, create two instances with different
names and ports.

Execute this module to start a DataCoordinator.
"""

from __future__ import annotations

import logging
import threading
from socket import gethostname
from types import TracebackType
from typing import Any

import zmq

from ..core import (
    COORDINATOR_PORT,
    PROXY_RECEIVING_PORT,
    PROXY_SENDING_PORT,
    PROXY_GATHERER_PORT,
    LOG_RECEIVING_PORT,
    LOG_SENDING_PORT,
    LOG_GATHERER_PORT,
)
from ..json_utils.errors import (
    GATHERER_ALREADY_CONNECTED,
    GATHERER_NOT_CONNECTED,
    JSONRPCError,
)
from ..utils.listener import Listener

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class DataCoordinator:
    """A Data Coordinator for multi-node data protocol distribution.

    Contains a Gatherer/Distributor proxy pair for a single data channel
    (data or log). Participates in the control protocol to allow dynamic
    configuration of remote Gatherer connections.

    For a complete multi-node setup, run two instances: one for data
    messages (default name ``DATA_COORDINATOR``) and one for log messages
    (default name ``LOG_COORDINATOR``).

    The namespace is determined automatically after signing in to the
    Control Coordinator via the Listener. It is not set in the constructor.

    Usage::

        with DataCoordinator(name="DATA_COORDINATOR") as dc:
            dc.run()

    :param str name: Component name (without namespace). Default "DATA_COORDINATOR".
    :param str host: Hostname or IP of this machine, used for addresses
        returned by :meth:`send_data_addresses` and for connecting to
        the Control Coordinator. Defaults to hostname.
    :param int coordinator_port: Port of the control Coordinator.
    :param int xsub_port: Port for Gatherer's XSUB (local publishers connect here).
    :param int gatherer_xpub_port: Port for Gatherer's XPUB (remote distributors connect here).
    :param int xpub_port: Port for Distributor's XPUB (local subscribers connect here).
    :param bool start_listener: Whether to start the control protocol listener.
    :param context: ZMQ context.
    """

    def __init__(
        self,
        name: str = "DATA_COORDINATOR",
        host: str | None = None,
        coordinator_port: int = COORDINATOR_PORT,
        xsub_port: int = PROXY_RECEIVING_PORT,
        gatherer_xpub_port: int = PROXY_GATHERER_PORT,
        xpub_port: int = PROXY_SENDING_PORT,
        start_listener: bool = True,
        context: zmq.Context | None = None,
        **kwargs: Any,
    ) -> None:
        self.name = name
        self.host = host or gethostname()
        self.closed = False

        if context is None:
            self.context = zmq.Context.instance()
            self._own_context = True
        else:
            self.context = context
            self._own_context = False

        self._xsub_port = xsub_port
        self._gatherer_xpub_port = gatherer_xpub_port
        self._xpub_port = xpub_port

        self._remote_gatherer_addresses: set[str] = set()

        self._proxy_threads: list[threading.Thread] = []
        self._control_sockets: list[zmq.Socket] = []

        self.gatherer_xsub, self.gatherer_xpub = self._setup_gatherer(
            xsub_port=xsub_port,
            xpub_port=gatherer_xpub_port,
        )
        self.distributor_xsub, self.distributor_xpub = self._setup_distributor(
            xpub_port=xpub_port,
            local_gatherer_xpub_port=gatherer_xpub_port,
        )

        if start_listener:
            self._setup_listener(host=self.host, port=coordinator_port, **kwargs)

        log.info(f"Starting DataCoordinator '{self.full_name}' at host '{self.host}'.")

    def _setup_gatherer(self, xsub_port: int, xpub_port: int) -> tuple[zmq.Socket, zmq.Socket]:
        xsub = self.context.socket(zmq.XSUB)
        xpub = self.context.socket(zmq.XPUB)
        xsub.bind(f"tcp://*:{xsub_port}")
        xpub.bind(f"tcp://*:{xpub_port}")
        log.info(f"Gatherer: XSUB on *:{xsub_port}, XPUB on *:{xpub_port}")
        self._start_proxy_thread(xsub, xpub, "gatherer")
        return xsub, xpub

    def _setup_distributor(
        self, xpub_port: int, local_gatherer_xpub_port: int
    ) -> tuple[zmq.Socket, zmq.Socket]:
        xsub = self.context.socket(zmq.XSUB)
        xpub = self.context.socket(zmq.XPUB)
        xsub.connect(f"tcp://localhost:{local_gatherer_xpub_port}")
        xpub.bind(f"tcp://*:{xpub_port}")
        log.info(
            f"Distributor: XSUB connected to localhost:{local_gatherer_xpub_port}, "
            f"XPUB on *:{xpub_port}"
        )
        self._start_proxy_thread(xsub, xpub, "distributor")
        return xsub, xpub

    def _start_proxy_thread(self, frontend: zmq.Socket, backend: zmq.Socket, name: str) -> None:
        control = self.context.socket(zmq.PAIR)
        control_addr = f"inproc://proxy-control-{self.name}-{name}"
        control.bind(control_addr)
        control_connect = self.context.socket(zmq.PAIR)
        control_connect.connect(control_addr)
        event = threading.Event()
        thread = threading.Thread(
            target=self._run_proxy,
            args=(frontend, backend, control, event),
            name=f"proxy-{self.name}-{name}",
            daemon=True,
        )
        thread.start()
        started = event.wait(2)
        if not started:
            raise TimeoutError(f"Proxy thread '{name}' failed to start.")
        self._proxy_threads.append(thread)
        self._control_sockets.append(control_connect)

    @staticmethod
    def _run_proxy(
        frontend: zmq.Socket,
        backend: zmq.Socket,
        control: zmq.Socket,
        event: threading.Event,
    ) -> None:
        event.set()
        try:
            zmq.proxy_steerable(frontend, backend, control=control)
        except zmq.ContextTerminated:
            pass
        except zmq.ZMQError as exc:
            log.warning(f"Proxy terminated with ZMQError: {exc}")

    def _setup_listener(self, host: str, port: int, **kwargs: Any) -> None:
        initial_name = f"{self.name}"
        self.listener = Listener(
            name=initial_name,
            host=host,
            port=port,
            **kwargs,
        )
        self.listener.start_listen()
        rpc = self.listener.message_handler.rpc
        rpc.unregister_method("shut_down")
        rpc.method()(self.shut_down)
        rpc.method()(self.connect_to_gatherer)
        rpc.method()(self.disconnect_from_gatherer)
        rpc.method()(self.list_gatherers)
        rpc.method()(self.send_data_addresses)
        self.listener.message_handler.register_on_name_change_method(self._on_name_change)

    @property
    def full_name(self) -> str:
        try:
            return self.listener.message_handler.full_name
        except AttributeError:
            return self.name

    def _on_name_change(self, full_name: str) -> None:
        log.info(f"DataCoordinator name updated to '{full_name}'.")

    def __del__(self) -> None:
        try:
            self.close()
        except AttributeError:
            pass

    def __enter__(self) -> DataCoordinator:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: TracebackType | None,
    ) -> bool | None:
        self.close()
        return None

    def close(self) -> None:
        if not self.closed:
            log.debug("Closing DataCoordinator.")
            if hasattr(self, "listener"):
                try:
                    self.listener.stop_listen()
                except Exception:
                    pass
            for control in self._control_sockets:
                try:
                    control.send(b"TERMINATE")
                except Exception:
                    pass
            for thread in self._proxy_threads:
                thread.join(timeout=2)
            for attr in ("gatherer_xsub", "gatherer_xpub", "distributor_xsub", "distributor_xpub"):
                sock = getattr(self, attr, None)
                if sock is not None:
                    try:
                        sock.close(linger=0)
                    except Exception:
                        pass
            for control in self._control_sockets:
                try:
                    control.close(linger=0)
                except Exception:
                    pass
            if self._own_context:
                try:
                    self.context.term()
                except Exception:
                    pass
            log.info(f"DataCoordinator '{getattr(self, 'full_name', '')}' closed.")
            self.closed = True

    def run(self, stop_event: threading.Event | None = None) -> None:
        """Block until stop_event is set or KeyboardInterrupt."""
        if stop_event is None:
            stop_event = threading.Event()
        try:
            stop_event.wait()
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    # Component protocol methods
    def shut_down(self) -> None:
        self.close()

    # Data Coordinator RPC methods
    def connect_to_gatherer(self, address: str) -> None:
        """Connect the local Distributor to a remote Gatherer's XPUB socket."""
        if address in self._remote_gatherer_addresses:
            raise JSONRPCError(GATHERER_ALREADY_CONNECTED.with_data(data=address))
        self.distributor_xsub.connect(f"tcp://{address}")
        self._remote_gatherer_addresses.add(address)
        log.info(f"Connected Distributor to remote Gatherer at '{address}'.")

    def disconnect_from_gatherer(self, address: str) -> None:
        """Disconnect the local Distributor from a remote Gatherer's XPUB socket."""
        if address not in self._remote_gatherer_addresses:
            raise JSONRPCError(GATHERER_NOT_CONNECTED.with_data(data=address))
        self.distributor_xsub.disconnect(f"tcp://{address}")
        self._remote_gatherer_addresses.discard(address)
        log.info(f"Disconnected Distributor from remote Gatherer at '{address}'.")

    def list_gatherers(self) -> list[str]:
        """List the addresses of remote Gatherers the local Distributor is connected to."""
        return sorted(self._remote_gatherer_addresses)

    def send_data_addresses(self) -> dict[str, str]:
        """Send the bound socket addresses of this Data Coordinator's Gatherer and Distributor."""
        return {
            "gatherer_xsub": f"{self.host}:{self._xsub_port}",
            "gatherer_xpub": f"{self.host}:{self._gatherer_xpub_port}",
            "distributor_xpub": f"{self.host}:{self._xpub_port}",
        }


def main() -> None:
    from argparse import ArgumentParser
    from pyleco.utils.parser import parse_command_line_parameters

    parser = ArgumentParser(prog="Data Coordinator")
    parser.add_argument(
        "--host",
        help="hostname of this machine and of the control Coordinator",
        default="localhost",
    )
    parser.add_argument(
        "-p",
        "--coordinator-port",
        type=int,
        default=COORDINATOR_PORT,
        help="port of the control Coordinator",
    )
    parser.add_argument(
        "--data-xsub-port",
        type=int,
        default=PROXY_RECEIVING_PORT,
        help="port for data Gatherer XSUB",
    )
    parser.add_argument(
        "--data-gatherer-xpub-port",
        type=int,
        default=PROXY_GATHERER_PORT,
        help="port for data Gatherer XPUB",
    )
    parser.add_argument(
        "--data-xpub-port",
        type=int,
        default=PROXY_SENDING_PORT,
        help="port for data Distributor XPUB",
    )
    parser.add_argument(
        "--log-xsub-port", type=int, default=LOG_RECEIVING_PORT, help="port for log Gatherer XSUB"
    )
    parser.add_argument(
        "--log-gatherer-xpub-port",
        type=int,
        default=LOG_GATHERER_PORT,
        help="port for log Gatherer XPUB",
    )
    parser.add_argument(
        "--log-xpub-port", type=int, default=LOG_SENDING_PORT, help="port for log Distributor XPUB"
    )
    parser.add_argument(
        "--data-gatherers",
        default="",
        help="comma separated list of remote data Gatherer XPUB addresses to connect to",
    )
    parser.add_argument(
        "--log-gatherers",
        default="",
        help="comma separated list of remote log Gatherer XPUB addresses to connect to",
    )
    parser.add_argument(
        "--no-log", action="store_true", default=False, help="do not start the log coordinator"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="increase the logging level by one, may be used more than once",
    )
    kwargs = parse_command_line_parameters(parser=parser, logger=log, logging_default=logging.INFO)
    no_log = kwargs.pop("no_log", False)
    host = kwargs.pop("host", "localhost")
    coordinator_port = kwargs.pop("coordinator_port", COORDINATOR_PORT)
    data_xsub_port = kwargs.pop("data_xsub_port", PROXY_RECEIVING_PORT)
    data_gatherer_xpub_port = kwargs.pop("data_gatherer_xpub_port", PROXY_GATHERER_PORT)
    data_xpub_port = kwargs.pop("data_xpub_port", PROXY_SENDING_PORT)
    log_xsub_port = kwargs.pop("log_xsub_port", LOG_RECEIVING_PORT)
    log_gatherer_xpub_port = kwargs.pop("log_gatherer_xpub_port", LOG_GATHERER_PORT)
    log_xpub_port = kwargs.pop("log_xpub_port", LOG_SENDING_PORT)
    data_gatherers = [a for a in kwargs.pop("data_gatherers", "").replace(" ", "").split(",") if a]
    log_gatherers = [a for a in kwargs.pop("log_gatherers", "").replace(" ", "").split(",") if a]

    context = zmq.Context()
    stop_event = threading.Event()
    try:
        data_dc = DataCoordinator(
            name="DATA_COORDINATOR",
            host=host,
            coordinator_port=coordinator_port,
            xsub_port=data_xsub_port,
            gatherer_xpub_port=data_gatherer_xpub_port,
            xpub_port=data_xpub_port,
            context=context,
            **kwargs,
        )
    except Exception:
        context.term()
        raise
    for address in data_gatherers:
        data_dc.connect_to_gatherer(address)
    if no_log:
        try:
            data_dc.run(stop_event=stop_event)
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            data_dc.close()
    else:
        try:
            log_dc = DataCoordinator(
                name="LOG_COORDINATOR",
                host=host,
                coordinator_port=coordinator_port,
                xsub_port=log_xsub_port,
                gatherer_xpub_port=log_gatherer_xpub_port,
                xpub_port=log_xpub_port,
                context=context,
                **kwargs,
            )
        except Exception:
            data_dc.close()
            context.term()
            raise
        for address in log_gatherers:
            log_dc.connect_to_gatherer(address)
        log_thread = threading.Thread(
            target=log_dc.run,
            args=(stop_event,),
            daemon=True,
        )
        log_thread.start()
        try:
            data_dc.run(stop_event=stop_event)
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            log_thread.join(timeout=5)
            log_dc.close()
            data_dc.close()


if __name__ == "__main__":
    main()
