#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
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

from abc import abstractmethod
from dataclasses import dataclass
import logging
from time import perf_counter
from typing import List, Dict, Tuple, Protocol, Optional

import zmq

from ..errors import CommunicationError
from ..core.enums import Commands, Errors
from ..core.message import Message
from ..core.serialization import deserialize_data


log = logging.getLogger()
log.addHandler(logging.NullHandler())


class MultiSocket(Protocol):
    """Represents a socket with multiple connections."""

    @abstractmethod
    def bind(self, host: str, port: int | str) -> None:
        raise NotImplementedError("Implement in subclass")

    @abstractmethod
    def unbind(self) -> None:
        raise NotImplementedError("Implement in subclass")

    @abstractmethod
    def close(self, timeout: float) -> None:
        raise NotImplementedError("Implement in subclass")

    @abstractmethod
    def send_message(self, identity: bytes, message: Message) -> None:
        raise NotImplementedError("Implement in subclass")

    @abstractmethod
    def message_received(self, timeout: float = 0) -> bool:
        raise NotImplementedError("Implement in subclass")

    @abstractmethod
    def read_message(self) -> Tuple[bytes, Message]:
        raise NotImplementedError("Implement in subclass")


class ZmqMultiSocket(MultiSocket):
    """A MultiSocket using a zmq ROUTER socket."""

    def __init__(self, context: Optional[zmq.Context] = None, *args, **kwargs) -> None:
        context = zmq.Context.instance() if context is None else context
        self._sock = context.socket(zmq.ROUTER)
        super().__init__(*args, **kwargs)

    def bind(self, host: str = "*", port: str | int = 12300) -> None:
        self._sock.bind(f"tcp://{host}:{port}")

    def unbind(self) -> None:
        self._sock.unbind()

    def close(self, timeout: float = 0) -> None:
        self._sock.close(linger=timeout)

    def send_message(self, identity: bytes, message: Message) -> None:
        self._sock.send_multipart((identity, *message.get_frames_list()))

    def message_received(self, timeout: float = 0) -> bool:
        return bool(self._sock.poll(timeout=timeout))

    def read_message(self) -> Tuple[bytes, Message]:
        identity, *response = self._sock.recv_multipart()
        return identity, Message.from_frames(*response)


class FakeMultiSocket(MultiSocket):
    """With a fake socket."""

    def __init__(self, *args, **kwargs) -> None:
        self._messages_read: List[Tuple[bytes, Message]] = []
        self._messages_sent: List[Tuple[bytes, Message]] = []
        super().__init__(*args, **kwargs)

    def bind(self, host: str = "*", port: int | str = 5) -> None:
        pass

    def unbind(self) -> None:
        pass

    def close(self, timeout: float) -> None:
        pass

    def send_message(self, identity: bytes, message: Message) -> None:
        self._messages_sent.append((identity, message))

    def message_received(self, timeout: float = 0) -> bool:
        return len(self._messages_read) > 0

    def read_message(self) -> Tuple[bytes, Message]:
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
        raise NotImplementedError("Implement in subclass")

    def is_connected(self) -> bool:
        return False

    def send_message(self, message: Message) -> None:
        raise NotImplementedError("Implement in subclass")

    def message_received(self, timeout: float = 0) -> bool:
        raise NotImplementedError("Implement in subclass")

    def read_message(self, timeout: int = 0) -> Message:
        raise NotImplementedError("Implement in subclass")


class ZmqNode(Node):
    """Represents a zmq connection to another node."""

    def __init__(self, context=None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._context = zmq.Context.instance() if context is None else context

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
        self._dealer.send_multipart(message.get_frames_list())

    def message_received(self, timeout: float = 0) -> bool:
        return bool(self._dealer.poll(timeout=timeout))

    def read_message(self, timeout: int = 0) -> Message | None:
        return Message.from_frames(*self._dealer.recv_multipart())


class FakeNode(Node):

    def __init__(self, messages_read: None | List[Message] = None, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._messages_sent: List[Message] = []
        self._messages_read: List[Message] = [] if messages_read is None else messages_read

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
        self._components: Dict[bytes, Component] = {}
        self._nodes: Dict[bytes, Node] = {}  # resolution from the namespace
        self._node_ids: Dict[bytes, Node] = {}  # resolution from the id
        self._waiting_nodes: Dict[str, Node] = {}
        self.namespace = namespace
        self.full_name = full_name
        self._address = address

    def add_component(self, name: bytes, identity: bytes) -> None:
        if name in self._components:
            raise ValueError("Component already present.")
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
            address = address + ":12300"
        if namespace == self.namespace or address == self._address:
            raise ValueError("Cannot connect to myself.")
        if namespace in self._nodes.keys():
            raise ValueError("Already connected.")
        if address in self._waiting_nodes.keys():
            raise ValueError("Already trying to connect.")
        node.heartbeat = perf_counter()
        node.connect(address)
        node.send_message(Message(receiver=b"COORDINATOR", sender=self.full_name,
                                  data=[[Commands.CO_SIGNIN]]))
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
                self._handle_node_message(key=key, msg=response)

    def _handle_node_message(self, key: str, msg: Message) -> None:
        data = deserialize_data(content=msg.payload[0])
        if data == [[Commands.ACKNOWLEDGE]]:
            self._finish_sign_in_to_remote(key=key, msg=msg)
        elif (data == [[Commands.ERROR, Errors.DUPLICATE_NAME]]
              or data == [[Commands.ERROR, Errors.NOT_SIGNED_IN]]):  # TODO due to log in to itself
            log.error(f"Coordinator Sign in to node {msg.sender_node} failed. My name was rejected.")  # noqa: E501
            self._remove_waiting_node(key=key)
        # TODO this is only useful, if we read the DEALER sockets regularly
        # elif data == [[Commands.ERROR, Errors.NOT_SIGNED_IN]]:
        #     # Somehow connection got lost, sign in again
        #     sock.send_multipart(create_message(receiver=b"COORDINATOR", sender=self.fname,
        #                                        payload=serialize_data([[Commands.CO_SIGNIN]])))
        else:
            log.warning(f"Unknown message {msg.payload} from {msg.sender} at DEALER socket {key}.")

    def _finish_sign_in_to_remote(self, key: str, msg: Message) -> None:
        node = self._waiting_nodes.pop(key)
        log.info(f"Renaming DEALER socket from temporary {key} to {msg.sender_node}.")
        self._nodes[msg.sender_node] = node
        node.namespace = msg.sender_node
        self._combine_sender_and_receiver_nodes(node=node)
        node.send_message(Message(
                receiver=msg.sender,
                sender=self.full_name,
                data=[[Commands.SET, {'directory': self.get_component_names(),
                                      'nodes': self.get_nodes_str_dict()}]]))

    def _combine_sender_and_receiver_nodes(self, node: Node) -> None:
        for identity, receiver_node in self._node_ids.items():
            if not receiver_node.is_connected() and receiver_node.namespace == node.namespace:
                node.heartbeat = receiver_node.heartbeat
                self._node_ids[identity] = node
                break

    def remove_node(self, namespace: bytes, identity: bytes) -> None:
        node = self._node_ids.get(identity)
        if node and node.namespace == namespace:
            self._remove_node_without_checks(namespace=namespace)
        else:
            raise CommunicationError(
                "Identities do not match.",
                error_payload=[Commands.ERROR, Errors.EXECUTION_FAILED, "You are not you!"])

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
        if message.sender_node == b"" or message.sender_node == self.namespace:
            self._update_local_sender_heartbeat(sender_identity=sender_identity, message=message)
        elif sender_identity in self._node_ids.keys():
            # Message from another Coordinator's DEALER socket
            self._node_ids[sender_identity].heartbeat = perf_counter()
        elif message.sender_name == b"COORDINATOR" and (
                message.payload == [f'[["{Commands.CO_SIGNIN}"]]'.encode()]
                or message.payload == [f'[["{Commands.CO_SIGNOUT}"]]'.encode()]):
            pass  # Signing in/out, no heartbeat yet
        else:
            # Either a Component communicates with the wrong namespace setting or
            # the other Coordinator is not known yet (reconnection)
            raise CommunicationError(
                f"Message {message.payload} from not signed in Component {message.sender_node}.{message.sender_name} or node.",  # noqa: E501
                error_payload=[[Commands.ERROR, Errors.NOT_SIGNED_IN]])

    def _update_local_sender_heartbeat(self, sender_identity: bytes, message: Message) -> None:
        component = self._components.get(message.sender_name)
        if component and sender_identity == component.identity:
            component.heartbeat = perf_counter()
        elif message.payload == [f'[["{Commands.SIGNIN}"]]'.encode()]:
            pass  # Signing in, no heartbeat yet
        else:
            raise CommunicationError(
                f"Message {message.payload} from not signed in Component {message.sender_node}.{message.sender_name}.",  # noqa: E501
                error_payload=[[Commands.ERROR, Errors.NOT_SIGNED_IN]])

    def find_expired_components(self, expiration_time: float) -> List[Tuple[bytes, bytes]]:
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
                self._remove_waiting_node(key=key)

    def _find_expired_connected_nodes(self, expiration_time: float) -> None:
        now = perf_counter()
        for identity, node in list(self._node_ids.items()):
            self._check_node_expiration(expiration_time, now, node=node, identity=identity)

    def _check_node_expiration(self, expiration_time: float, now: float,
                               node: Node,
                               identity: bytes = b"",
                               ) -> None:
        if now > node.heartbeat + 3 * expiration_time:
            log.info(f"Node {node} at {identity} is unresponsive, removing.")
            self._remove_node_without_checks(namespace=node.namespace)
        elif now > node.heartbeat + expiration_time:
            if node.is_connected():
                log.debug(f"Node {node} expired with identity {identity}, pinging.")
                node.send_message(Message(
                    receiver=node.namespace + b".COORDINATOR",
                    sender=self.full_name,
                    data=[[Commands.PING]]))

    def get_components(self) -> Dict[bytes, Component]:
        return self._components

    def get_component_names(self) -> List[str]:
        return [key.decode() for key in self._components.keys()]

    def get_component_id(self, name: bytes) -> bytes:
        try:
            return self._components[name].identity
        except KeyError:
            raise ValueError(f"Component {name} is not known.")

    def get_node(self, namespace: bytes) -> Node:
        try:
            return self._nodes[namespace]
        except KeyError:
            raise ValueError("Node not known.")

    def get_node_id(self, namespace: bytes) -> bytes:
        for id, node in self._node_ids.items():
            if node.namespace == namespace:
                return id
        raise ValueError(f"No receiving connection to namespace {namespace} found.")

    def get_nodes(self) -> Dict[bytes, Node]:
        return self._nodes

    def get_nodes_str_dict(self) -> Dict[str, str]:
        nodes = {self.namespace.decode(): self._address}
        for key, node in self._nodes.items():
            nodes[key.decode()] = node.address
        return nodes

    def get_node_ids(self) -> Dict[bytes, Node]:
        return self._node_ids

    def send_node_message(self, namespace: bytes, message: Message) -> None:
        try:
            node = self._nodes[namespace]
        except KeyError:
            raise ValueError(f"Node {namespace} is not known.")
        else:
            node.send_message(message)

    def sign_out_from_node(self, namespace: bytes) -> None:
        try:
            node = self._nodes[namespace]
        except KeyError:
            raise ValueError("Node is not known.")
        node.send_message(Message(
            receiver=b".".join((namespace, b"COORDINATOR")),
            sender=self.full_name,
            data=[[Commands.CO_SIGNOUT]],
            ))
        node.disconnect()
        self._remove_node_without_checks(namespace)

    def sign_out_from_all_nodes(self) -> None:
        nodes = list(self._nodes.keys())
        log.info(
            f"Signing out from fellow Coordinators: {', '.join([n.decode() for n in nodes])}.")
        for namespace in nodes:
            self.sign_out_from_node(namespace=namespace)
