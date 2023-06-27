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

import logging
from socket import gethostname
from typing import List, Optional

from jsonrpcobjects.objects import ErrorResponseObject, RequestObject, RequestObjectParams
from openrpc import RPCServer
import zmq

try:
    from ..utils.coordinator_utils import Directory, ZmqNode, ZmqMultiSocket
    from ..core.message import Message
    from ..errors import CommunicationError
    from ..errors import NODE_UNKNOWN, RECEIVER_UNKNOWN, generate_error_with_data
    from ..utils.timers import RepeatingTimer
    from ..utils.zmq_log_handler import ZmqLogHandler
except ImportError as exc:
    from pyleco.utils.coordinator_utils import Directory, ZmqNode, ZmqMultiSocket
    from pyleco.core.message import Message
    from pyleco.errors import CommunicationError
    from pyleco.errors import NODE_UNKNOWN, RECEIVER_UNKNOWN, generate_error_with_data
    from pyleco.utils.timers import RepeatingTimer
    from pyleco.utils.zmq_log_handler import ZmqLogHandler

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

    def __init__(self, namespace: str | bytes | None = None,
                 host: str | None = None, port: int = 12300,
                 timeout: int = 50, cleaning_interval: float = 5,
                 expiration_time: float = 15,
                 context=None,
                 multi_socket=None,
                 **kwargs) -> None:
        if namespace is None:
            self.namespace = gethostname().encode()
        elif isinstance(namespace, str):
            self.namespace = namespace.encode()
        elif isinstance(namespace, bytes):
            self.namespace = namespace
        else:
            raise ValueError("`node` must be str or bytes or None.")
        self.fname = self.namespace + b".COORDINATOR"
        log.info(f"Start Coordinator of node {self.namespace} at port {port}.")
        self.address = f"{gethostname() if host is None else host}:{port}"
        self.directory = Directory(namespace=self.namespace, full_name=self.fname,
                                   address=self.address)
        self.global_directory = {}  # All Components
        self.timeout = timeout
        self.cleaner = RepeatingTimer(interval=cleaning_interval, function=self.clean_addresses,
                                      args=(expiration_time,))

        self.cleaner.start()

        context = zmq.Context.instance() if context is None else context
        self.sock = ZmqMultiSocket(context) if multi_socket is None else multi_socket
        self.context = context
        self.sock.bind(port=port)

        self.register_methods()

        super().__init__(**kwargs)

    def register_methods(self):
        """Add methods to the OpenRPC register and change the name."""
        rpc = RPCServer(title="COORDINATOR", debug=True)
        rpc.title = self.fname.decode()
        rpc.method(self.sign_in)
        rpc.method(self.sign_out)
        rpc.method(self.coordinator_sign_in)
        rpc.method(self.coordinator_sign_out)
        rpc.method(self.set_nodes)
        rpc.method(self.set_remote_components)
        rpc.method(self.set_log_level)
        rpc.method(self.compose_global_directory)
        rpc.method(self.compose_local_directory, description=self.compose_local_directory.__doc__)
        rpc.method(self.directory.get_component_names)
        rpc.method(self.clean_addresses, description=self.clean_addresses.__doc__)
        rpc.method(self.shutdown)
        rpc.method(self.pong)
        self.rpc = rpc

    def __del__(self) -> None:
        self.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        self.close()

    def close(self) -> None:
        """Sign out and close the sockets."""
        log.debug("Closing Coordinator.")
        if not self.closed:
            self.sign_out_from_all_coordinators()
            self.sock.close(1)
            self.cleaner.cancel()
            log.info(f"Coordinator {self.fname} closed.")
            self.closed = True

    def create_message(self, receiver: bytes, data: Optional[bytes | str | object] = None,
                       **kwargs) -> Message:
        return Message(receiver=receiver, sender=self.fname, data=data, **kwargs)

    def send_message(self, receiver: bytes, data: object = None, **kwargs) -> None:
        """Send a message with any socket, including routing.

        :param receiver: Receiver name
        :param data: Object to send.
        :param \\**kwargs: Keyword arguments for the header.
        """
        self.deliver_message(sender_identity=b"",
                             message=Message(receiver=receiver, sender=self.fname, data=data,
                                             **kwargs))

    def send_main_sock_reply(self, sender_identity: bytes, original_message: Message,
                             data: Optional[bytes | str | object] = None) -> None:
        response = self.create_message(receiver=original_message.sender,
                                       data=data,
                                       conversation_id=original_message.conversation_id,)
        self.sock.send_message(sender_identity, response)

    def clean_addresses(self, expiration_time: float) -> None:
        """Clean all expired addresses from the directory.

        :param float expiration_time: Expiration limit in s.
        """
        log.debug("Cleaning addresses.")
        self._clean_components(expiration_time=expiration_time)
        self.directory.find_expired_nodes(expiration_time=expiration_time)

    def _clean_components(self, expiration_time: float) -> None:
        to_admonish = self.directory.find_expired_components(expiration_time=expiration_time)
        for identity, name in to_admonish:
            message = self.create_message(receiver=b".".join((self.namespace, name)),
                                          data=RequestObject(id=0, method="pong"))
            self.sock.send_message(identity, message)
        self.publish_directory_update()

    def routing(self, coordinators: Optional[List[str]] = None) -> None:
        """Route all messages.

        Connect to Coordinators at the beginning.

        :param list coordinators: list of coordinator addresses.
        """
        # Connect to Coordinators.
        if coordinators is not None:
            for coordinator in coordinators:
                self.directory.add_node_sender(node=ZmqNode(context=self.context),
                                               address=coordinator, namespace=b"")
        # Route messages until told to stop.
        self.running = True
        while self.running:
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
        log.debug(f"From identity {sender_identity}, from {message.sender}, to {message.receiver},"
                  f" mid {message.message_id}, cid {message.conversation_id}, {message.payload}")
        # Update heartbeat
        if sender_identity:
            try:
                self.directory.update_heartbeat(sender_identity=sender_identity, message=message)
            except CommunicationError as exc:
                log.error(str(exc))
                self.send_main_sock_reply(sender_identity=sender_identity,
                                          original_message=message,
                                          data=exc.error_payload)
                return
        # Route the message
        if message.receiver_node != self.namespace and message.receiver_node != b"":
            # remote connections.
            try:
                self.directory.send_node_message(namespace=message.receiver_node, message=message)
            except ValueError:
                error = generate_error_with_data(NODE_UNKNOWN, data=message.receiver_node_str)
                self.send_message(receiver=message.sender,
                                  data=ErrorResponseObject(id=None, error=error),
                                  conversation_id=message.conversation_id,
                                  )
        elif message.receiver_name == b"COORDINATOR":
            # Coordinator communication
            self.handle_commands(sender_identity=sender_identity, message=message)
        else:
            try:
                receiver_identity = self.directory.get_component_id(name=message.receiver_name)
            except ValueError:
                log.error(f"Receiver '{message.receiver}' is not in the addresses list.")
                error = generate_error_with_data(RECEIVER_UNKNOWN, data=message.receiver_str)
                self.send_message(receiver=message.sender, conversation_id=message.conversation_id,
                                  data=ErrorResponseObject(id=None, error=error),
                                  )
            else:
                self.sock.send_message(receiver_identity, message)

    def handle_commands(self, sender_identity: bytes, message: Message) -> None:
        """Handle commands for the Coordinator itself.

        :param bytes sender_identity: Identity of the original sender.
        :param Message message: The message object.
        """
        if not message.payload:
            return  # Empty payload, just heartbeat.
        self.current_message = message
        self.current_identity = sender_identity
        if b'"jsonrpc"' in message.payload[0]:
            log.warning(f"Message {message} as command!")
            log.debug(f"Coordinator json commands: {message.payload[0]}")
            if b'"method":' in message.payload[0]:
                self.handle_rpc_call(sender_identity=sender_identity, message=message)
            elif b'"error"' in message.payload[0]:
                log.error(f"Error from {message.sender} received: {message.payload[0]}.")
            elif b'"result": null' in message.payload[0]:
                pass  # acknowledgement == heartbeat
            else:
                log.error(f"Unknown message from {message.sender} received: {message.payload[0]}")
            return
        else:
            # TODO raise an error?
            log.error(f"Unknown message from {message.sender} received: {message.payload[0]}")

    def handle_rpc_call(self, sender_identity: bytes, message: Message) -> None:
        reply = self.rpc.process_request(message.payload[0])
        log.debug(f"Reply {repr(reply)} to {message.sender} at node {message.sender_node}.")
        if (message.sender_node == self.namespace or message.sender_node == b""):
            self.send_main_sock_reply(sender_identity=sender_identity, original_message=message,
                                      data=reply)
        else:
            reply_message = Message(receiver=message.sender,
                                    conversation_id=message.conversation_id, data=reply)
            self.deliver_message(sender_identity=b"", message=reply_message)

    def sign_in(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        self.directory.add_component(name=message.sender_name, identity=sender_identity)
        log.info(f"New Component {message.sender_name} at {sender_identity}.")
        self.publish_directory_update()

    def sign_out(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        self.directory.remove_component(name=message.sender_name, identity=sender_identity)
        log.info(f"Component {message.sender_name} signed out.")
        self.publish_directory_update()

    def coordinator_sign_in(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        sender_node = message.sender_node
        message.sender = message.sender_name  # remove node in order to respond via main socket
        self.directory.add_node_receiver(identity=sender_identity,
                                         namespace=sender_node)

    def coordinator_sign_out(self) -> None:
        message = self.current_message
        sender_identity = self.current_identity
        assert message.sender_name == b"COORDINATOR", (
            "Only Coordinators may use coordinator sign out.")
        node = self.directory.get_node(namespace=message.sender_node)
        self.directory.remove_node(namespace=message.sender_node, identity=sender_identity)
        node.send_message(Message(
                receiver=message.sender_node + b".COORDINATOR",
                sender=self.fname,
                conversation_id=message.conversation_id,
                data=RequestObject(id=100, method="coordinator_sign_out")
            ))

    def set_nodes(self, nodes: dict) -> None:  # : Dict[str, str]
        for node, address in nodes.items():
            node = node.encode()
            try:
                self.directory.add_node_sender(ZmqNode(context=self.context),
                                               address=address, namespace=node)
            except ValueError:
                pass  # already connected

    def set_remote_components(self, components: List[str]) -> None:
        message = self.current_message
        self.global_directory[message.sender_node] = components

    @staticmethod
    def set_log_level(level: int) -> None:
        log.setLevel(level)

    def sign_out_from_all_coordinators(self) -> None:
        """Sign out from other Coordinators."""
        self.directory.sign_out_from_all_nodes()

    def compose_local_directory(self) -> dict:
        """Compose a dictionary with the local directory."""
        return {'directory': self.directory.get_component_names(),
                'nodes': self.directory.get_nodes_str_dict()}

    def compose_global_directory(self) -> dict:
        """Compose a dictionary with the global directory."""
        data = {ns.decode(): components for ns, components in self.global_directory.items()}
        local = self.compose_local_directory()
        # TODO TBD how to encapsulate nodes information
        data['nodes'] = local['nodes']
        data[self.namespace.decode()] = local['directory']
        return data

    def publish_directory_update(self) -> None:
        """Send a directory update to the other coordinators."""
        # TODO TBD whether to send the whole directory or only a diff.
        directory = self.compose_local_directory()
        for node in self.directory.get_nodes().keys():
            # self.send_message(receiver=b".".join((node, b"COORDINATOR")),
            #                   data=[[Commands.SET, directory]])
            self.send_message(
                receiver=b".".join((node, b"COORDINATOR")),
                data=[RequestObjectParams(id=2, method="set_nodes",
                                          params={"nodes": directory.get("nodes", {})}).dict(),
                      RequestObjectParams(
                        id=3, method="set_remote_components",
                        params={"components": directory.get("directory", [])}).dict()])

    def shutdown(self) -> None:
        self.running = False
        self.sign_out_from_all_coordinators()

    def pong(self) -> None:
        """Respond in order to test the connection"""
        pass


if __name__ == "__main__":
    # Absolute imports if the file is executed.
    from argparse import ArgumentParser  # noqa: F811
    from pyleco.utils.parser import parse_command_line_parameters  # noqa: F811

    # Define parser
    parser = ArgumentParser()
    parser.add_argument("-c", "--coordinators", default="",
                        help="connect to this comma separated list of coordinators")
    parser.add_argument("--host", help="set the host name of this Coordinator")
    parser.add_argument("-n", "--namespace", help="set the Node's namespace")
    parser.add_argument("-q", "--quiet", action="count", default=0,
                        help="decrease the logging level by one, may be used more than once")
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="increase the logging level by one, may be used more than once")
    parser.add_argument("-p", "--port", type=int, help="port number to bind to")

    # Parse and interpret command line parameters
    kwargs = parse_command_line_parameters(logger=log, parser=parser, logging_default=logging.INFO)
    if len(log.handlers) <= 1:
        log.addHandler(logging.StreamHandler())
    cos = kwargs.pop('coordinators', "")
    coordinators = cos.replace(" ", "").split(",")

    # Run the coordinator
    with Coordinator(**kwargs) as c:
        handler = ZmqLogHandler()
        handler.fullname = c.fname.decode()
        log.addHandler(handler)
        c.routing(coordinators=coordinators)
