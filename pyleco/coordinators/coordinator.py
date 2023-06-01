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

import zmq

try:
    from ..utils.coordinator_utils import Directory, ZmqNode, ZmqMultiSocket
    from ..core.enums import Commands, Errors
    from ..core.message import Message
    from ..core.serialization import deserialize_data
    from ..errors import CommunicationError
    from ..utils.timers import RepeatingTimer
    from ..utils.zmq_log_handler import ZmqLogHandler
except ImportError as exc:
    import_error = exc
    from pyleco.core.message import Message
else:
    import_error = None

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
        self.closed = False

        context = zmq.Context.instance() if context is None else context
        self.sock = ZmqMultiSocket(context) if multi_socket is None else multi_socket
        self.context = context
        self.sock.bind(port=port)

        super().__init__(**kwargs)

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
            self.sign_out()
            self.sock.close(1)
            self.cleaner.cancel()
            log.info(f"Coordinator {self.fname} closed.")
            self.closed = True

    def create_message(self, receiver: bytes, data: object = None, **kwargs) -> Message:
        return Message(receiver=receiver, sender=self.fname, data=data, **kwargs)

    def send_message(self, receiver: bytes, data: object = None, **kwargs) -> None:
        """Send a message with any socket, including routing.

        :param identity: Connection identity to send to.
        :param receiver: Receiver name
        :param data: Object to send.
        :param \\**kwargs: Keyword arguments for the header.
        """
        self.deliver_message(sender_identity=b"",
                             message=Message(receiver=receiver, sender=self.fname, data=data,
                                             **kwargs))

    def send_main_sock_reply(self, sender_identity: bytes, original_message: Message,
                             data: object = None) -> None:
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
                                          data=[[Commands.PING]])
            self.sock.send_message(identity, message)
        self.publish_directory_update()

    def routing(self, coordinators: list | None = None) -> None:
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
        """Deliver a message `msg` from some `sender_identity` to some recipient."""
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
                self.send_message(receiver=message.sender,
                                  data=[[Commands.ERROR, Errors.NODE_UNKNOWN,
                                         message.receiver_node.decode()]],
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
                self.send_message(receiver=message.sender, conversation_id=message.conversation_id,
                                  data=[[Commands.ERROR, Errors.RECEIVER_UNKNOWN,
                                         message.receiver.decode()]])
            else:
                self.sock.send_message(receiver_identity, message)

    def handle_commands(self, sender_identity: bytes, message: Message) -> None:
        """Handle commands for the Coordinator itself.

        :param bytes sender_identity: Identity of the original sender.
        :param Message message: The message object.
        """
        if not message.payload:
            return  # Empty payload, just heartbeat.
        try:
            data = deserialize_data(content=message.payload[0])
        except ValueError as exc:
            log.exception("Payload decoding error.", exc_info=exc)
            return  # TODO error message
        log.debug(f"Coordinator commands: {data}")
        reply = []
        try:
            for command in data:  # type: ignore due to try clause
                if not command:
                    continue  # nothing to handle.
                elif command[0] == Commands.ACKNOWLEDGE:
                    # Handle requestes responses.
                    # No requests implemented yet.
                    return  # A response should not cause an answer
                # Component sign-in / sign-out
                elif command[0] == Commands.SIGNIN:
                    try:
                        self.directory.add_component(name=message.sender_name,
                                                     identity=sender_identity)
                    except ValueError:
                        log.info(f"Another Component at {sender_identity} "
                                 f"tries to sign in as {message.sender_name}.")
                        self.send_main_sock_reply(sender_identity=sender_identity,
                                                  original_message=message,
                                                  data=[[Commands.ERROR, Errors.DUPLICATE_NAME]])
                        return
                    else:
                        log.info(f"New Component {message.sender_name} at {sender_identity}.")
                        reply.append([Commands.ACKNOWLEDGE])
                        self.publish_directory_update()
                elif command[0] == Commands.SIGNOUT:
                    try:
                        self.directory.remove_component(name=message.sender_name,
                                                        identity=sender_identity)
                    except ValueError:
                        self.send_main_sock_reply(sender_identity=sender_identity,
                                                  original_message=message,
                                                  data=[[Commands.ERROR, Errors.NAME_NOT_FOUND]])
                    else:
                        reply.append([Commands.ACKNOWLEDGE])
                        log.info(f"Component {message.sender_name} signed out.")
                        self.publish_directory_update()
                # Coordinator sign-in / sign-out
                elif command[0] == Commands.CO_SIGNIN:
                    try:
                        self.directory.add_node_receiver(identity=sender_identity,
                                                         namespace=message.sender_node)
                    except ValueError:
                        log.info(f"Another Coordinator at {sender_identity} "
                                 f"tries to sign in as {message.sender}.")
                        self.send_main_sock_reply(sender_identity=sender_identity,
                                                  original_message=message,
                                                  data=[[Commands.ERROR, Errors.DUPLICATE_NAME]])
                    else:
                        self.send_main_sock_reply(sender_identity=sender_identity,
                                                  original_message=message,
                                                  data=[[Commands.ACKNOWLEDGE]])
                    return
                elif command[0] == Commands.CO_SIGNOUT and message.sender_name == b"COORDINATOR":
                    try:
                        node = self.directory.get_node(namespace=message.sender_node)
                    except ValueError:
                        log.warning(f"Not signed in Coordinator {message.sender_node} signs out.")
                        return  # TBD what to do, if it is not known
                    try:
                        self.directory.remove_node(namespace=message.sender_node,
                                                   identity=sender_identity)
                    except CommunicationError as exc:
                        self.send_main_sock_reply(sender_identity=sender_identity,
                                                  original_message=message,
                                                  data=[exc.error_payload])
                    else:
                        node.send_message(Message(
                            receiver=message.sender_node + b".COORDINATOR",
                            sender=self.fname,
                            conversation_id=message.conversation_id,
                            data=[[Commands.CO_SIGNOUT]],
                        ))
                    return
                # Control the Coordinator itself
                elif command[0] == Commands.OFF:
                    self.running = False
                    self.sign_out()
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.CLEAR:
                    self.clean_addresses(0)
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.LIST:
                    reply.append([Commands.ACKNOWLEDGE, self.compose_global_directory()])
                elif command[0] == Commands.SET:
                    for key, value in command[1].items():
                        if key == "directory":
                            # TODO assumes to receive always full updates, no diffs
                            self.global_directory[message.sender_node] = value
                        elif key == "nodes":
                            for node, address in value.items():
                                node = node.encode()
                                try:
                                    self.directory.add_node_sender(ZmqNode(context=self.context),
                                                                   address=address, namespace=node)
                                except ValueError:
                                    pass  # already connected
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.GET:
                    if len(command) > 1 and isinstance(command[1], (list, tuple)):
                        data = {}
                        for prop in command[1]:
                            if prop == "directory":
                                data["directory"] = self.directory.get_component_names()
                            elif prop == "nodes":
                                data["nodes"] = self.compose_local_directory()["nodes"]
                        reply.append([Commands.ACKNOWLEDGE, data])
                    else:
                        reply.append([Commands.ERROR, Errors.EXECUTION_FAILED])
                elif command[0] == Commands.LOG:
                    log.setLevel(command[1])
                    reply.append([Commands.ACKNOWLEDGE])
        except Exception as exc:
            log.exception("Handling commands failed.", exc_info=exc)
        log.debug(f"Reply {reply} to {message.sender} at node {message.sender_node}.")
        if message.sender_node == self.namespace or message.sender_node == b"":
            self.send_main_sock_reply(sender_identity=sender_identity, original_message=message,
                                      data=reply)
        else:
            self.send_message(receiver=message.sender, conversation_id=message.conversation_id,
                              data=reply)

    def sign_out(self) -> None:
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
            self.send_message(receiver=b".".join((node, b"COORDINATOR")),
                              data=[[Commands.SET, directory]])


if __name__ == "__main__":
    # Absolute imports if the file is executed.
    from argparse import ArgumentParser  # noqa: F811
    from pyleco.utils.coordinator_utils import Directory, ZmqNode, ZmqMultiSocket  # noqa: F811
    from pyleco.core.enums import Commands, Errors  # noqa: F811
    from pyleco.core.message import Message  # noqa: F811
    from pyleco.core.serialization import deserialize_data  # noqa: F811
    from pyleco.errors import CommunicationError  # noqa: F811
    from pyleco.utils.timers import RepeatingTimer  # noqa: F811
    from pyleco.utils.zmq_log_handler import ZmqLogHandler  # noqa: F811
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
elif import_error is not None:
    # Raise the error, if the file is not executed.
    raise import_error
