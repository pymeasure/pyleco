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
from json import JSONDecodeError
import logging
from socket import gethostname
from typing import Any, Optional, Union

import zmq

if __name__ != "__main__":
    from ..core import COORDINATOR_PORT
    from ..utils.coordinator_utils import CommunicationError, Directory, ZmqNode, ZmqMultiSocket,\
        MultiSocket
    from ..core.message import Message, MessageTypes
    from ..core.serialization import get_json_content_type, JsonContentTypes
    from ..json_utils.errors import NODE_UNKNOWN, RECEIVER_UNKNOWN
    from ..json_utils.json_objects import ErrorResponse, Request, ParamsRequest, DataError
    from ..json_utils.rpc_server import RPCServer
    from ..utils.timers import RepeatingTimer
    from ..utils.zmq_log_handler import ZmqLogHandler
    from ..utils.events import Event, SimpleEvent
    from ..utils.log_levels import PythonLogLevels
else:  # pragma: no cover
    from pyleco.core import COORDINATOR_PORT
    from pyleco.utils.coordinator_utils import CommunicationError, Directory, ZmqNode,\
          ZmqMultiSocket, MultiSocket
    from pyleco.core.message import Message, MessageTypes
    from pyleco.core.serialization import get_json_content_type, JsonContentTypes
    from pyleco.json_utils.errors import NODE_UNKNOWN, RECEIVER_UNKNOWN
    from pyleco.json_utils.json_objects import ErrorResponse, Request, ParamsRequest, DataError
    from pyleco.json_utils.rpc_server import RPCServer
    from pyleco.utils.timers import RepeatingTimer
    from pyleco.utils.zmq_log_handler import ZmqLogHandler
    from pyleco.utils.events import Event, SimpleEvent
    from pyleco.utils.log_levels import PythonLogLevels

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Coordinator:
    """A Coordinator program, routing messages among connected peers.

    .. code::

        with Coordinator() as coordinator:
            coordinator.routing()

    :param str namespace: Name of the node. Defaults to hostname.
    :param str host: Hostname of the system of this Coordinator, that others may connect to it.
    :param int port: Port to listen to.
    :param timeout: Timeout waiting for messages in ms.
    :param cleaning_interval: Interval between two addresses cleaning runs in s.
    :param expiration_time: Time, when a stored address expires in s.
    :param context: ZMQ context or similar.
    """

    current_message: Message
    current_identity: bytes
    closed: bool = False

    def __init__(
        self,
        namespace: Optional[Union[bytes, str]] = None,
        host: Optional[str] = None,
        port: int = COORDINATOR_PORT,
        timeout: int = 50,
        cleaning_interval: float = 5,
        expiration_time: float = 15,
        context: Optional[zmq.Context] = None,
        multi_socket: Optional[MultiSocket] = None,
        **kwargs,
    ) -> None:
        if namespace is None:
            self.namespace = gethostname().split(".")[0].encode()
        elif isinstance(namespace, str):
            self.namespace = namespace.encode()
        elif isinstance(namespace, bytes):
            self.namespace = namespace
        else:
            raise ValueError("`namespace` must be str or bytes or None.")
        self.full_name = self.namespace + b".COORDINATOR"
        log.info(f"Start Coordinator of node {self.namespace!r} at port '{port}'.")
        self.address = f"{host or gethostname()}:{port}"
        self.directory = Directory(
            namespace=self.namespace, full_name=self.full_name, address=self.address
        )
        self.global_directory: dict[bytes, list[str]] = {}  # All Components
        self.timeout = timeout
        self.cleaner = RepeatingTimer(
            interval=cleaning_interval,
            function=self.remove_expired_addresses,
            args=(expiration_time,),
        )

        self.cleaner.start()

        context = context or zmq.Context.instance()
        self.sock = multi_socket or ZmqMultiSocket(context=context)
        self.context = context
        self.sock.bind(port=port)

        self.register_methods()

        super().__init__(**kwargs)

    def register_methods(self):
        """Add methods to the OpenRPC register and change the name."""
        self.rpc = rpc = RPCServer(title="COORDINATOR", debug=True)
        rpc.title = self.full_name.decode()
        # Component
        rpc.method()(self.pong)
        # Extended Component
        rpc.method()(self.set_log_level)
        rpc.method()(self.shut_down)
        # Coordinator proper
        rpc.method()(self.sign_in)
        rpc.method()(self.sign_out)
        rpc.method()(self.coordinator_sign_in)
        rpc.method()(self.coordinator_sign_out)
        rpc.method()(self.add_nodes)
        rpc.method()(self.send_nodes)
        rpc.method()(self.record_components)
        rpc.method()(self.send_local_components)
        rpc.method()(self.send_global_components)
        rpc.method(description=self.remove_expired_addresses.__doc__)(self.remove_expired_addresses)

    def __del__(self) -> None:
        try:
            self.close()
        except AttributeError:
            pass  # if creation failed, closing may fail during deletion.

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        """Sign out and close the sockets."""
        log.debug("Closing Coordinator.")
        if not self.closed:
            self.shut_down()
            self.sock.close(timeout=1)
            self.cleaner.cancel()
            log.info(f"Coordinator {self.full_name!r} closed.")
            self.closed = True

    def create_message(
        self, receiver: bytes, data: Optional[Union[bytes, str, object]] = None, **kwargs
    ) -> Message:
        return Message(receiver=receiver, sender=self.full_name, data=data, **kwargs)

    def send_message(self, receiver: bytes, data: Optional[object] = None, **kwargs) -> None:
        """Send a message with any socket, including routing.

        :param receiver: Receiver name
        :param data: Object to send.
        :param \\**kwargs: Keyword arguments for the header.
        """
        self.deliver_message(
            sender_identity=b"",
            message=self.create_message(receiver=receiver, data=data, **kwargs),
        )

    def send_main_sock_reply(
        self,
        sender_identity: bytes,
        original_message: Message,
        data: Optional[Union[bytes, str, object]] = None,
        message_type: Optional[Union[bytes, int, MessageTypes]] = None,
    ) -> None:
        response = self.create_message(
            receiver=original_message.sender,
            conversation_id=original_message.conversation_id,
            data=data,
            message_type=message_type,
        )
        self.sock.send_message(sender_identity, response)

    def remove_expired_addresses(self, expiration_time: float) -> None:
        """Remove all expired addresses from the directory.

        :param float expiration_time: Expiration limit in s.
        """
        log.debug("Cleaning addresses.")
        self._clean_components(expiration_time=expiration_time)
        self.directory.find_expired_nodes(expiration_time=expiration_time)

    def _clean_components(self, expiration_time: float) -> None:
        to_admonish = self.directory.find_expired_components(expiration_time=expiration_time)
        for identity, name in to_admonish:
            message = self.create_message(
                receiver=b".".join((self.namespace, name)),
                message_type=MessageTypes.JSON,
                data=Request(id=0, method="pong"),
            )
            self.sock.send_message(identity, message)
        self.publish_directory_update()

    def routing(
        self, coordinators: Optional[list[str]] = None, stop_event: Optional[Event] = None
    ) -> None:
        """Route all messages.

        Connect to Coordinators at the beginning.

        :param list coordinators: list of coordinator addresses.
        """
        # Connect to Coordinators.
        if coordinators is not None:
            for coordinator in coordinators:
                self.directory.add_node_sender(
                    node=ZmqNode(context=self.context), address=coordinator, namespace=b""
                )
        # Route messages until told to stop.
        self.stop_event = stop_event or SimpleEvent()
        while not self.stop_event.is_set():
            if self.sock.message_received(self.timeout):
                self.read_and_route()
            self.directory.check_unfinished_node_connections()
        # Cleanup
        log.info("Coordinator routing stopped.")

    def read_and_route(self) -> None:
        """Do the routing of one message."""
        try:
            sender_identity, message = self.sock.read_message()
        except TypeError as exc:
            log.exception("Not enough frames read.", exc_info=exc)
            return
        else:
            # Handle different communication cases.
            self.deliver_message(sender_identity=sender_identity, message=message)

    def deliver_message(self, sender_identity: bytes, message: Message) -> None:
        """Deliver a message `message` from some `sender_identity` to some recipient.

        Messages from this Coordinator must have :code:`sender_identity = b""`.
        """
        log.debug(
            f"From identity {sender_identity!r}, from {message.sender!r}, to {message.receiver!r},"
            f" header {message.header!r}, cid {message.conversation_id!r}, '{message.payload}'."
        )
        # Update heartbeat
        if sender_identity:
            try:
                self.directory.update_heartbeat(sender_identity=sender_identity, message=message)
            except CommunicationError as exc:
                log.error(f"Updating heartbeat of {message.sender!r} failed due to '{exc}'.")
                self.send_main_sock_reply(
                    sender_identity=sender_identity,
                    original_message=message,
                    message_type=MessageTypes.JSON,
                    data=exc.error_payload,
                )
                return
        # Route the message
        receiver_namespace, receiver_name = message.receiver_elements
        if message.receiver == b"COORDINATOR" or message.receiver == self.full_name:
            self.handle_commands(sender_identity=sender_identity, message=message)
        elif receiver_namespace == self.namespace or receiver_namespace == b"":
            self._deliver_locally(message=message, receiver_name=receiver_name)
        else:
            self._deliver_remotely(message=message, receiver_namespace=receiver_namespace)

    def _deliver_locally(self, message: Message, receiver_name: bytes) -> None:
        try:
            receiver_identity = self.directory.get_component_id(name=receiver_name)
        except ValueError:
            log.error(f"Receiver '{message.receiver!r}' is not in the addresses list.")
            error = DataError.from_error(RECEIVER_UNKNOWN, data=message.receiver.decode())
            self.send_message(
                receiver=message.sender,
                conversation_id=message.conversation_id,
                message_type=MessageTypes.JSON,
                data=ErrorResponse(id=None, error=error),
            )
        else:
            self.sock.send_message(receiver_identity, message)

    def _deliver_remotely(self, message: Message, receiver_namespace: bytes) -> None:
        try:
            self.directory.send_node_message(namespace=receiver_namespace, message=message)
        except ValueError:
            error = DataError.from_error(NODE_UNKNOWN, data=receiver_namespace.decode())
            self.send_message(
                receiver=message.sender,
                conversation_id=message.conversation_id,
                message_type=MessageTypes.JSON,
                data=ErrorResponse(id=None, error=error),
            )

    def handle_commands(self, sender_identity: bytes, message: Message) -> None:
        """Handle commands for the Coordinator itself.

        :param bytes sender_identity: Identity of the original sender.
        :param Message message: The message object.
        """
        if not message.payload:
            return  # Empty payload, just heartbeat.
        self.current_message = message
        self.current_identity = sender_identity
        if message.header_elements.message_type == MessageTypes.JSON:
            self.handle_json_commands(message=message)
        else:
            log.error(
                f"Message from {message.sender!r} of unknown type received: {message.payload[0]!r}"
            )

    def handle_json_commands(self, message: Message) -> None:
        try:
            data: Union[list[dict[str, Any]], dict[str, Any]] = message.data  # type: ignore
        except JSONDecodeError:
            log.error(
                f"Invalid JSON message from {message.sender!r} received: {message.payload[0]!r}"
            )
            return
        json_type = get_json_content_type(data)
        if JsonContentTypes.REQUEST in json_type:
            try:
                self.handle_rpc_call(message=message)
            except Exception as exc:
                log.exception(
                    f"Invalid JSON-RPC message from {message.sender!r} received: {data}",
                    exc_info=exc,
                )
        elif JsonContentTypes.RESULT_RESPONSE == json_type:
            if data.get("result", False) is not None:  # type: ignore
                log.info(f"Unexpeced result received: {data}")
        elif JsonContentTypes.ERROR in json_type:
            log.error(f"Error from {message.sender!r} received: {data}.")
        elif JsonContentTypes.RESULT in json_type:
            for element in data:
                if element.get("result", False) is not None:  # type: ignore
                    log.info(f"Unexpeced result received: {data}")
        else:
            log.error(
                f"Invalid JSON RPC message from {message.sender!r} received: {message.payload[0]!r}"
            )  # noqa

    def handle_rpc_call(self, message: Message) -> None:
        reply = self.rpc.process_request(message.payload[0])
        sender_namespace = message.sender_elements.namespace
        log.debug(f"Reply {reply!r} to {message.sender!r} at node {sender_namespace!r}.")
        if sender_namespace == self.namespace or sender_namespace == b"":
            self.send_main_sock_reply(
                sender_identity=self.current_identity,
                original_message=message,
                data=reply,
                message_type=MessageTypes.JSON,
            )
        else:
            self.send_message(
                receiver=message.sender,
                conversation_id=message.conversation_id,
                message_type=MessageTypes.JSON,
                data=reply,
            )

    # Component procedures
    def pong(self) -> None:
        """Respond in order to test the connection"""
        pass

    @staticmethod
    def set_log_level(level: str) -> None:
        plevel = PythonLogLevels[level]
        log.setLevel(plevel)

    def shut_down(self) -> None:
        self.sign_out_from_all_coordinators()
        try:
            self.stop_event.set()
        except AttributeError:  # pragma: no cover
            pass

    # Coordinator procedures
    def sign_in(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        sender_name = message.sender_elements.name
        self.directory.add_component(name=sender_name, identity=sender_identity)
        log.info(f"New Component {sender_name!r} at {sender_identity!r}.")
        self.publish_directory_update()

    def sign_out(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        sender_name = message.sender_elements.name
        self.directory.remove_component(name=sender_name, identity=sender_identity)
        log.info(f"Component {sender_name!r} signed out.")
        self.publish_directory_update()

    def coordinator_sign_in(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        sender_namespace, sender_name = message.sender_elements
        message.sender = sender_name  # remove namespace in order to respond via main socket
        self.directory.add_node_receiver(identity=sender_identity, namespace=sender_namespace)

    def coordinator_sign_out(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        sender_namespace, sender_name = message.sender_elements
        assert sender_name == b"COORDINATOR", "Only Coordinators may use coordinator sign out."
        node = self.directory.get_node(namespace=sender_namespace)
        self.directory.remove_node(namespace=sender_namespace, identity=sender_identity)
        node.send_message(
            Message(
                receiver=sender_namespace + b".COORDINATOR",
                sender=self.full_name,
                conversation_id=message.conversation_id,
                message_type=MessageTypes.JSON,
                data=Request(id=100, method="coordinator_sign_out"),
            )
        )

    def add_nodes(self, nodes: dict) -> None:  # : dict[str, str]
        for node, address in nodes.items():
            node = node.encode()
            try:
                self.directory.add_node_sender(
                    ZmqNode(context=self.context), address=address, namespace=node
                )
            except ValueError:
                pass  # already connected

    def record_components(self, components: list[str]) -> None:
        """Record Components of another Coordinator."""
        message = self.current_message
        self.global_directory[message.sender_elements.namespace] = components

    def send_nodes(self) -> dict[str, str]:
        return self.directory.get_nodes_str_dict()

    def send_local_components(self) -> list[str]:
        """Send the names of locally connected Components."""
        return self.directory.get_component_names()

    def send_global_components(self) -> dict[str, list[str]]:
        """Send the names of all Components in this LECO network."""
        data = {ns.decode(): components for ns, components in self.global_directory.items()}
        data[self.namespace.decode()] = self.send_local_components()
        return data

    # Additional procedures
    def sign_out_from_all_coordinators(self) -> None:
        """Sign out from other Coordinators."""
        self.directory.sign_out_from_all_nodes()

    def publish_directory_update(self) -> None:
        """Send a directory update to the other coordinators."""
        # TODO TBD whether to send the whole directory or only a diff.
        nodes = self.directory.get_nodes_str_dict()
        components = self.directory.get_component_names()
        for node in self.directory.get_nodes().keys():
            self.send_message(
                receiver=b".".join((node, b"COORDINATOR")),
                message_type=MessageTypes.JSON,
                data=[
                    ParamsRequest(id=5, method="add_nodes", params={"nodes": nodes}).model_dump(),
                    ParamsRequest(
                        id=6, method="record_components", params={"components": components}
                    ).model_dump(),
                ],
            )


def main() -> None:
    # Absolute imports if the file is executed.
    from pyleco.utils.parser import parser, parse_command_line_parameters  # noqa: F811

    # Define parser
    parser.add_argument(
        "-c",
        "--coordinators",
        default="",
        help="connect to this comma separated list of coordinators",
    )
    parser.add_argument("--namespace", help="set the Node's namespace")
    parser.add_argument("-p", "--port", type=int, help="port number to bind to")

    # Parse and interpret command line parameters
    gLog = logging.getLogger()
    kwargs = parse_command_line_parameters(logger=gLog, parser=parser, logging_default=logging.INFO)
    if len(log.handlers) <= 1:
        log.addHandler(logging.StreamHandler())
    cos = kwargs.pop("coordinators", "")
    coordinators = cos.replace(" ", "").split(",")

    # Run the Coordinator
    with Coordinator(**kwargs) as c:
        handler = ZmqLogHandler(full_name=c.full_name.decode())
        gLog.addHandler(handler)
        c.routing(coordinators=coordinators)


if __name__ == "__main__":  # pragma: no cover
    main()
