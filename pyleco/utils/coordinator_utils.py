#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2025 PyLECO Developers
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
from abc import abstractmethod
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import Any, Protocol, Optional, Union

import zmq

from ..core import COORDINATOR_PORT
from ..core.message import Message, MessageTypes
from ..core.serialization import deserialize_data
from ..json_utils.errors import NOT_SIGNED_IN, DUPLICATE_NAME
from ..json_utils.rpc_generator import RPCGenerator
from ..json_utils.json_objects import ErrorResponse, Request


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class CommunicationError(ConnectionError):
    """Something went wrong, send an `error_msg` to the recipient."""

    def __init__(self, text: str, error_payload: ErrorResponse, *args: Any) -> None:
        super().__init__(text, *args)
        self.error_payload = error_payload


class MultiSocket(Protocol):
    """Represents a socket with multiple connections."""

    closed: bool = False

    @abstractmethod
    def bind(self, host: str = "", port: Union[int, str] = 0) -> None: ...  # pragma: no cover

    @abstractmethod
    def unbind(self) -> None: ...  # pragma: no cover

    @abstractmethod
    def close(self, timeout: int) -> None: ...  # pragma: no cover

    @abstractmethod
    def send_message(self, identity: bytes, message: Message) -> None: ...  # pragma: no cover

    @abstractmethod
    def message_received(self, timeout: int = 0) -> bool: ...  # pragma: no cover

    @abstractmethod
    def read_message(self) -> tuple[bytes, Message]: ...  # pragma: no cover


class ZmqMultiSocket(MultiSocket):
    """A MultiSocket using a zmq ROUTER socket."""

    def __init__(self, context: Optional[zmq.Context] = None, *args, **kwargs) -> None:
        context = zmq.Context.instance() if context is None else context
        self._sock: zmq.Socket = context.socket(zmq.ROUTER)
        super().__init__(*args, **kwargs)

    @property
    def closed(self) -> bool:  # type: ignore[override]
        return self._sock.closed  # type: ignore

    def bind(self, host: str = "*", port: Union[str, int] = COORDINATOR_PORT) -> None:
        self._sock.bind(f"tcp://{host}:{port}")

    def unbind(self) -> None:
        # TODO add the right address
        self._sock.unbind("")

    def close(self, timeout: int = 0) -> None:
        self._sock.close(linger=timeout)

    def send_message(self, identity: bytes, message: Message) -> None:
        self._sock.send_multipart((identity, *message.to_frames()))

    def message_received(self, timeout: int = 0) -> bool:
        return bool(self._sock.poll(timeout=timeout))

    def read_message(self) -> tuple[bytes, Message]:
        identity, *response = self._sock.recv_multipart()
        return identity, Message.from_frames(*response)


class FakeMultiSocket(MultiSocket):
    def __init__(self, *args, **kwargs) -> None:
        self._messages_read: list[tuple[bytes, Message]] = []
        self._messages_sent: list[tuple[bytes, Message]] = []
        super().__init__(*args, **kwargs)

    def bind(self, host: str = "*", port: Union[int, str] = 5) -> None:
        pass

    def unbind(self) -> None:
        pass  # pragma: no cover

    def close(self, timeout: int) -> None:
        self.closed = True  # pragma: no cover

    def send_message(self, identity: bytes, message: Message) -> None:
        self._messages_sent.append((identity, message))

    def message_received(self, timeout: int = 0) -> bool:
        return len(self._messages_read) > 0  # pragma: no cover

    def read_message(self) -> tuple[bytes, Message]:
        return self._messages_read.pop(0)


@dataclass
class Component:
    """A component connected to the Coordinator."""

    identity: bytes
    heartbeat: float


class Node:
    """Represents a connection to another Node."""

    def __init__(self, **kwargs) -> None:
        self.address: str = ""
        self.namespace: bytes = b""
        self.heartbeat: float = -1
        super().__init__(**kwargs)

    def connect(self, address: str) -> None:
        self.address = address

    def disconnect(self, closing_time=None) -> None:
        raise NotImplementedError("Implement in subclass")  # pragma: no cover

    def is_connected(self) -> bool:
        return False

    def send_message(self, message: Message) -> None:
        raise NotImplementedError("Implement in subclass")  # pragma: no cover

    def message_received(self, timeout: int = 0) -> bool:
        raise NotImplementedError("Implement in subclass")  # pragma: no cover

    def read_message(self, timeout: int = 0) -> Message:
        raise NotImplementedError("Implement in subclass")  # pragma: no cover


class ZmqNode(Node):
    """Represents a zmq connection to another node."""

    def __init__(self, context: Optional[zmq.Context] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._context = context or zmq.Context.instance()

    def connect(self, address: str) -> None:
        """Connect to a Coordinator at address."""
        super().connect(address)
        self._dealer = self._context.socket(zmq.DEALER)
        self._dealer.connect(f"tcp://{address}")

    def disconnect(self, closing_time=None) -> None:
        """Close the connection to the Coordinator."""
        try:
            self._dealer.close(linger=closing_time)
            del self._dealer
        except AttributeError:
            pass  # already deleted.

    def is_connected(self) -> bool:
        try:
            return not self._dealer.closed
        except AttributeError:
            return False

    def send_message(self, message: Message) -> None:
        """Send a multipart message to the Coordinator."""
        self._dealer.send_multipart(message.to_frames())

    def message_received(self, timeout: int = 0) -> bool:
        return bool(self._dealer.poll(timeout=timeout))

    def read_message(self, timeout: int = 0) -> Message:
        return Message.from_frames(*self._dealer.recv_multipart())


class FakeNode(Node):
    def __init__(self, messages_read: Optional[list[Message]] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._messages_sent: list[Message] = []
        self._messages_read: list[Message] = [] if messages_read is None else messages_read

    def connect(self, address) -> None:
        super().connect(address)
        self._connected = True

    def disconnect(self, closing_time=None) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    def send_message(self, message: Message) -> None:
        self._messages_sent.append(message)

    def message_received(self, timeout: float = 0) -> bool:
        return bool(len(self._messages_read))

    def read_message(self, timeout: int = 0) -> Message:
        return self._messages_read.pop(0)


class Directory:
    """Maintains the directory with all the connected Components and Coordinators."""

    def __init__(self, namespace: bytes, full_name: bytes, address: str) -> None:
        self._components: dict[bytes, Component] = {}
        self._nodes: dict[bytes, Node] = {}  # resolution from the namespace
        self._node_ids: dict[bytes, Node] = {}  # resolution from the id
        self._waiting_nodes: dict[str, Node] = {}
        self.namespace = namespace
        self.full_name = full_name
        self._address = address
        self.rpc_generator = RPCGenerator()

    def add_component(self, name: bytes, identity: bytes) -> None:
        if (component := self._components.get(name)):
            if component.identity == identity:
                component.heartbeat = perf_counter()
            else:
                log.error(f"Cannot add component {name!r} as the name is already taken.")
                raise ValueError(DUPLICATE_NAME.message)
        self._components[name] = Component(identity=identity, heartbeat=perf_counter())

    def remove_component(self, name: bytes, identity: Optional[bytes]) -> None:
        component = self._components.get(name)
        if component is None:
            return  # already removed.
        elif identity and component.identity != identity:
            raise ValueError("Identities do not match.")
        del self._components[name]

    def add_node_sender(self, node: Node, address: str, namespace: bytes) -> None:
        """Add an sending connection to that node, unless already connected to that namespace."""
        if ":" not in address:
            address = f"{address}:{COORDINATOR_PORT}"
        if namespace == self.namespace or address == self._address:
            raise ValueError("Cannot connect to myself.")
        if namespace in self._nodes.keys():
            raise ValueError("Already connected.")
        if address in self._waiting_nodes.keys():
            raise ValueError("Already trying to connect.")
        log.info(f"Signing in to remote node ad '{address}'.")
        node.heartbeat = perf_counter()
        node.connect(address)
        # node.send_message(Message(receiver=b"COORDINATOR", sender=self.full_name,
        #                           data=[[Commands.CO_SIGNIN]]))
        node.send_message(
            message=Message(
                receiver=b"COORDINATOR",
                sender=self.full_name,
                message_type=MessageTypes.JSON,
                data=self.rpc_generator.build_request_str(method="coordinator_sign_in"),
            )
        )
        self._waiting_nodes[address] = node

    def add_node_receiver(self, identity: bytes, namespace: bytes) -> None:
        """Add a receiving connection to the node."""
        node = self._nodes.get(namespace)
        if node is None:
            node = Node()
            node.namespace = namespace
        elif node in self._node_ids.values():
            raise ValueError("Another Coordinator is known!")
        node.heartbeat = perf_counter()
        self._node_ids[identity] = node

    def check_unfinished_node_connections(self) -> None:
        for key, node in list(self._waiting_nodes.items()):
            if node.message_received():
                try:
                    response = node.read_message()
                except TypeError as exc:
                    log.exception("Message decoding failed.", exc_info=exc)
                    continue
                self._handle_node_message(key=key, message=response)

    def _handle_node_message(self, key: str, message: Message) -> None:
        data = deserialize_data(content=message.payload[0])
        if isinstance(data, dict) and data.get("result", False) is None:
            self._finish_sign_in_to_remote(key=key, message=message)
        elif isinstance(data, dict) and (error := data.get("error") is not None):
            log.error(f"Coordinator sign in to node {message.sender_elements.namespace!r} failed with '{error}'.")  # noqa: E501
            self._remove_waiting_node(key=key)
        else:
            log.warning(
                f"Unknown message {message.payload!r} from {message.sender!r} at DEALER socket '{key}'.")  # noqa: E501

    def _finish_sign_in_to_remote(self, key: str, message: Message) -> None:
        node = self._waiting_nodes.pop(key)
        sender_namespace = message.sender_elements.namespace
        log.info(f"Renaming DEALER socket from temporary '{key}' to {sender_namespace!r}.")
        self._nodes[sender_namespace] = node
        node.namespace = sender_namespace
        self._combine_sender_and_receiver_nodes(node=node)
        node.send_message(
            Message(
                receiver=message.sender,
                sender=self.full_name,
                message_type=MessageTypes.JSON,
                data=(
                    "["
                    + self.rpc_generator.build_request_str(
                        method="add_nodes", nodes=self.get_nodes_str_dict()
                    )
                    + ", "
                    + self.rpc_generator.build_request_str(
                        method="record_components", components=self.get_component_names()
                    )
                    + "]"
                ),
            )
        )

    def _combine_sender_and_receiver_nodes(self, node: Node) -> None:
        for identity, receiver_node in self._node_ids.items():
            if not receiver_node.is_connected() and receiver_node.namespace == node.namespace:
                node.heartbeat = receiver_node.heartbeat
                self._node_ids[identity] = node
                log.debug(f"Combining the receiver information to node {node.namespace!r}.")
                break

    def remove_node(self, namespace: bytes, identity: bytes) -> None:
        node = self._node_ids.get(identity)
        if node and node.namespace == namespace:
            self._remove_node_without_checks(namespace=namespace)
        else:
            raise ValueError("Identities do not match: You are not you!")

    def _remove_node_without_checks(self, namespace: bytes) -> None:
        node = self._nodes.get(namespace)
        if node is None:
            for key, node in list(self._node_ids.items()):
                if node.namespace == namespace:
                    del self._node_ids[key]
                    break
        else:
            del self._nodes[namespace]
            self._remove_value_from_dict(value=node, dictionary=self._node_ids)

    def _remove_value_from_dict(self, value, dictionary: dict) -> None:
        for key, v in list(dictionary.items()):
            if value == v:
                del dictionary[key]

    def _remove_waiting_node(self, key: str) -> None:
        del self._waiting_nodes[key]

    def update_heartbeat(self, sender_identity: bytes, message: Message) -> None:
        sender = message.sender_elements
        if sender.namespace == b"" or sender.namespace == self.namespace:
            self._update_local_sender_heartbeat(sender_identity=sender_identity, message=message)
        elif sender_identity in self._node_ids.keys():
            # Message from another Coordinator's DEALER socket
            self._node_ids[sender_identity].heartbeat = perf_counter()
        elif (
            sender.name == b"COORDINATOR"
            and message.payload
            and b"coordinator_sign_" in message.payload[0]  # "method": "
        ):
            pass  # Coordinator signing in/out, no heartbeat yet
        else:
            # Either a Component communicates with the wrong namespace setting or
            # the other Coordinator is not known yet (reconnection)
            raise CommunicationError(
                f"Message payload '{message.payload}' from not signed in Component {message.sender!r} or node.",  # noqa: E501
                error_payload=ErrorResponse(id=None, error=NOT_SIGNED_IN))

    def _update_local_sender_heartbeat(self, sender_identity: bytes, message: Message) -> None:
        component = self._components.get(message.sender_elements.name)
        if component:
            if sender_identity == component.identity:
                component.heartbeat = perf_counter()
            else:
                raise CommunicationError(
                    DUPLICATE_NAME.message,
                    error_payload=ErrorResponse(id=None, error=DUPLICATE_NAME)
                )
        elif message.payload and (b'"sign_in"' in message.payload[0]
                                  or b'"sign_out"' in message.payload[0]):
            pass  # Signing in, no heartbeat yet
        else:
            raise CommunicationError(
                f"Message payload '{message.payload}' from not signed in Component {message.sender!r}.",  # noqa: E501
                error_payload=ErrorResponse(id=None, error=NOT_SIGNED_IN))

    def find_expired_components(self, expiration_time: float) -> list[tuple[bytes, bytes]]:
        """Find expired components, return those to admonish, and remove those too old."""
        now = perf_counter()
        to_admonish = []
        for name, component in list(self._components.items()):
            if now > component.heartbeat + 3 * expiration_time:
                self.remove_component(name=name, identity=None)
            elif now > component.heartbeat + expiration_time:
                to_admonish.append((component.identity, name))
        return to_admonish

    def find_expired_nodes(self, expiration_time: float) -> None:
        """Find expired nodes, admonish or remove them."""
        self._find_expired_connected_nodes(expiration_time)
        self._find_expired_waiting_nodes(expiration_time)

    def _find_expired_waiting_nodes(self, expiration_time: float) -> None:
        now = perf_counter()
        for key, node in list(self._waiting_nodes.items()):
            if now > node.heartbeat + 3 * expiration_time:
                log.info(f"Removing unresponsive node at address '{key}'.")
                self._remove_waiting_node(key=key)

    def _find_expired_connected_nodes(self, expiration_time: float) -> None:
        now = perf_counter()
        for identity, node in list(self._node_ids.items()):
            self._check_node_expiration(expiration_time, now, node=node, identity=identity)

    def _check_node_expiration(
        self,
        expiration_time: float,
        now: float,
        node: Node,
        identity: bytes = b"",
    ) -> None:
        if now > node.heartbeat + 3 * expiration_time:
            log.info(f"Node {node.namespace!r} at {identity!r} is unresponsive, removing.")
            self._remove_node_without_checks(namespace=node.namespace)
        elif now > node.heartbeat + expiration_time:
            if node.is_connected():
                log.debug(f"Node {node.namespace!r} expired with identity {identity!r}, pinging.")
                node.send_message(
                    Message(
                        receiver=node.namespace + b".COORDINATOR",
                        sender=self.full_name,
                        message_type=MessageTypes.JSON,
                        data=Request(id=0, method="pong"),
                    )
                )

    def get_components(self) -> dict[bytes, Component]:
        return self._components

    def get_component_names(self) -> list[str]:
        return [key.decode() for key in self._components.keys()]

    def get_component_id(self, name: bytes) -> bytes:
        try:
            return self._components[name].identity
        except KeyError:
            raise ValueError(f"Component {name!r} is not known.")

    def get_node(self, namespace: bytes) -> Node:
        try:
            return self._nodes[namespace]
        except KeyError:
            raise ValueError("Node not known.")

    def get_node_id(self, namespace: bytes) -> bytes:
        for id, node in self._node_ids.items():
            if node.namespace == namespace:
                return id
        raise ValueError(f"No receiving connection to namespace {namespace!r} found.")

    def get_nodes(self) -> dict[bytes, Node]:
        return self._nodes

    def get_nodes_str_dict(self) -> dict[str, str]:
        nodes = {self.namespace.decode(): self._address}
        for key, node in self._nodes.items():
            nodes[key.decode()] = node.address
        return nodes

    def get_node_ids(self) -> dict[bytes, Node]:
        return self._node_ids

    def send_node_message(self, namespace: bytes, message: Message) -> None:
        try:
            node = self._nodes[namespace]
        except KeyError:
            raise ValueError(f"Node {namespace!r} is not known.")
        else:
            node.send_message(message)

    def sign_out_from_node(self, namespace: bytes) -> None:
        try:
            node = self._nodes[namespace]
        except KeyError:
            raise ValueError("Node is not known.")
        node.send_message(
            Message(
                receiver=b".".join((namespace, b"COORDINATOR")),
                sender=self.full_name,
                message_type=MessageTypes.JSON,
                data=self.rpc_generator.build_request_str(method="coordinator_sign_out"),
            )
        )
        node.disconnect()
        self._remove_node_without_checks(namespace)

    def sign_out_from_all_nodes(self) -> None:
        nodes = list(self._nodes.keys())
        log.info(f"Signing out from fellow Coordinators: {', '.join([n.decode() for n in nodes])}.")
        for namespace in nodes:
            self.sign_out_from_node(namespace=namespace)
