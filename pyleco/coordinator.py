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
from random import random
from socket import gethostname
import sys
from time import perf_counter

import zmq

from .utils import (Commands, serialize_data, interpret_header, create_message,
                    split_name, deserialize_data, divide_message,
                    )
from .timers import RepeatingTimer


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Coordinator:
    """A Coordinator program, routing messages among connected peers.

    .. code::

        c = Coordinator()
        c.routing()

    :param str node: Name of the node. Defaults to hostname
    :param int port: Port to listen to.
    :param timeout: Timeout waiting for messages in ms.
    :param cleaning_interval: Interval between two addresses cleaning runs in s.
    :param expiration_time: Time, when a stored address expires in s.
    :param context: ZMQ context or similar.
    """

    def __init__(self, node=None, host=None, port=12300, timeout=50, cleaning_interval=5, expiration_time=15,
                 context=zmq.Context.instance(),
                 **kwargs):
        if node is None:
            self.node = gethostname().encode()
        elif isinstance(node, str):
            self.node = node.encode()
        elif isinstance(node, bytes):
            self.node = node
        else:
            raise ValueError("`node` must be str or bytes or None.")
        self.fname = self.node + b".COORDINATOR"
        log.info(f"Start Coordinator of node {self.node} at port {port}.")
        self.address = (gethostname() if host is None else host, port)
        # Connected Components
        self.directory = {b'COORDINATOR': b""}  # Component name: identity
        self.heartbeats = {}  # Component name: timestamp
        # Connected Coordinators
        self.node_identities = {}  # identity: Namespace
        self.node_heartbeats = {}  # identity: time
        self.dealers = {}  # Namespace: DEALER socket
        self.waiting_dealers = {}  # Namespace, socket
        self.node_addresses = {self.node: self.address}  # Namespace: address
        self.global_directory = {}  # All Components
        self.timeout = timeout
        self.cleaner = RepeatingTimer(cleaning_interval, self.clean_addresses, args=(expiration_time,))

        self.context = context
        self.sock = self.context.socket(zmq.ROUTER)
        self.cleaner.start()
        try:
            self.sock.bind(f"tcp://*:{port}")
        except Exception:
            raise
        super().__init__(**kwargs)

    def __del__(self):
        self.close()

    def close(self):
        self.sock.close(1)
        self.cleaner.cancel()

    def send_message(self, receiver, data=None, **kwargs):
        """Send a message with any socket, including routing.

        :param identity: Connection identity to send to.
        :param receiver: Receiver name
        :param sender: Sender name
        :param data: Object to send.
        :param \\**kwargs: Keyword arguments for the header.
        """
        payload = [serialize_data(data)] if data else None
        frames = create_message(receiver, self.fname, payload=payload, **kwargs)
        self.deliver_message(b"", frames)

    def send_message_raw(self, sender_identity, receiver, data=None, **kwargs):
        """Send a message with the ROUTER socket.

        :param identity: Connection identity to send to.
        :param receiver: Receiver name
        :param sender: Sender name
        :param data: Object to send.
        :param \\**kwargs: Keyword arguments for the header.
        """
        payload = [serialize_data(data)] if data else None
        frames = create_message(receiver, self.fname, payload=payload, **kwargs)
        self.sock.send_multipart((sender_identity, *frames))

    def clean_addresses(self, expiration_time):
        """Clean all expired addresses.

        :param float expiration_time: Expiration limit in s.
        """
        log.debug("Cleaning addresses.")
        now = perf_counter()
        for name, time in list(self.heartbeats.items()):
            if now > time + 2 * expiration_time:
                del self.directory[name]
                del self.heartbeats[name]
            elif now > time + expiration_time:
                self.send_message_raw(self.directory[name], receiver=b".".join((self.node, name)),
                                      data=[[Commands.PING]])
        # Clean Coordinators
        for identity, time in list(self.node_heartbeats.items()):
            if now > time + 2 * expiration_time:
                del self.node_heartbeats[identity]
                node = self.node_identities.get(identity, None)
                if node is not None:
                    log.debug(f"Node {node} at {identity} is unresponsive, removing.")
                    try:
                        self.dealers[node].close(1)
                        del self.dealers[node]
                        del self.waiting_dealers[node]
                    except KeyError:
                        pass
                del self.node_identities[identity]
            elif now > time + expiration_time:
                node = self.node_identities.get(identity, None)
                log.debug(f"Node {node} expired with identity {identity}, pinging.")
                if node is None:
                    del self.node_heartbeats[identity]
                    continue
                self.send_message(receiver=node + b".COORDINATOR", data=[[Commands.PING]])

    def routing(self, coordinators=[]):
        """Route all messages.

        Connect to Coordinators at the beginning.
        :param list coordinators: list of coordinator addresses (host, port).
        """
        for coordinator in coordinators:
            self.add_coordinator(*coordinator)
        self.running = True
        while self.running:
            if self.sock.poll(self.timeout):
                self._routing()
            for ns, sock in list(self.waiting_dealers.items()):
                if sock.poll(0):
                    self.handle_dealer_message(sock, ns)
        # Cleanup
        log.info("Coordinator stopped.")

    def _routing(self):
        """Do the routing of one message."""
        sender_identity, *msg = self.sock.recv_multipart()
        # Handle different communication cases.
        self.deliver_message(sender_identity, msg)

    def deliver_message(self, sender_identity, msg):
        """Deliver a message to some recipient"""
        try:
            version, receiver, sender, header, payload = divide_message(msg)
        except IndexError:
            log.error(f"Less than two frames received! {msg}.")
            return
        conversation_id, message_id = interpret_header(header)
        log.debug(f"From identity {sender_identity}, from {sender}, to {receiver}, {message_id}, {payload}")
        r_node, r_name = split_name(receiver, self.node)
        s_node, s_name = split_name(sender, self.node)
        # Update heartbeat
        if sender_identity:
            if s_node == self.node:
                if sender_identity == self.directory.get(s_name):
                    self.heartbeats[s_name] = perf_counter()
                elif payload == [f'[["{Commands.SIGNIN}"]]'.encode()]:
                    pass  # Signing in, no heartbeat yet
                else:
                    log.error(f"Message {payload} from not signed in Component {sender}.")
                    self.send_message_raw(sender_identity, sender, conversation_id=conversation_id,
                                          data=[[Commands.ERROR, "You did not sign in!"]])
                    return
            elif s_name == b"COORDINATOR" or sender_identity in self.node_identities.keys():
                # Message from another Coordinator's DEALER socket
                self.node_heartbeats[sender_identity] = perf_counter()
            else:
                log.error(f"Not signed in component {sender} tries to send a message.")
                self.send_message_raw(sender_identity, receiver=sender, conversation_id=conversation_id,
                                      data=[[Commands.ERROR, "You did not sign in!"]])
                return
        # Route the message
        if r_node != self.node:
            # remote connections.
            try:
                self.dealers[r_node].send_multipart(msg)
            except KeyError:
                self.send_message(receiver=sender,
                                  data=[[Commands.ERROR, f"Node {r_node} is not known."]])
        elif r_name == b"COORDINATOR" or r_name == b"":
            # Coordinator communication
            self.handle_commands(sender_identity, sender, s_node, s_name, conversation_id, payload)
        elif receiver_addr := self.directory.get(r_name):
            # Local Receiver is known
            self.sock.send_multipart((receiver_addr, *msg))
        else:
            # Receiver is unknown
            log.error(f"Receiver '{receiver}' is not in the addresses list.")
            self.send_message(receiver=sender, conversation_id=conversation_id,
                              data=[[Commands.ERROR, f"Receiver '{receiver}' is not in addresses list."]])

    def handle_commands(self, sender_identity, sender, s_node, s_name, conversation_id, payload):
        """Handle commands for the Coordinator itself."""
        if not payload:
            return  # Empty payload, just heartbeat.
        try:
            data = deserialize_data(payload[0])
        except ValueError as exc:
            log.exception("Payload decoding error.", exc_info=exc)
            return  # TODO error message
        log.debug(f"Coordinator commands: {data}")
        reply = []
        try:
            for command in data:
                if not command:
                    continue
                elif command[0] == Commands.SIGNIN:
                    if s_name not in self.directory.keys():
                        log.info(f"New Component {s_name} at {sender_identity}.")
                        reply.append([Commands.ACKNOWLEDGE])
                        self.directory[s_name] = sender_identity
                        self.heartbeats[s_name] = perf_counter()
                    else:
                        log.info(f"Another Component at {sender_identity} tries to log in as {s_name}.")
                        self.send_message_raw(sender_identity, receiver=sender,
                                              conversation_id=conversation_id,
                                              data=[[Commands.ERROR, Commands.SIGNIN, "The name is already taken."]])
                        return
                elif command[0] == Commands.OFF:
                    self.running = False
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.CLEAR:
                    self.clean_addresses(0)
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.LIST:
                    reply.append(self.compose_local_directory())
                elif command[0] == Commands.SIGNOUT and sender_identity == self.directory.get(s_name):
                    try:
                        del self.directory[s_name]
                        del self.heartbeats[s_name]
                    except KeyError:
                        pass  # no entry
                    reply.append([Commands.ACKNOWLEDGE])
                elif command[0] == Commands.CO_SIGNIN and s_node not in self.dealers.keys():
                    self.node_identities[sender_identity] = s_node
                    self.send_message_raw(sender_identity, receiver=sender,
                                          conversation_id=conversation_id,
                                          data=[[Commands.ACKNOWLEDGE]])
                    return
                elif command[0] == Commands.SET:
                    for key, value in command[1].items():
                        if key == "directory":
                            self.global_directory[s_node] = value
                        elif key == "nodes":
                            for node, address in value.items():
                                node = node.encode()
                                if node in self.dealers.keys() or node == self.node:
                                    continue
                                self.add_coordinator(*address, node=node)
        except Exception as exc:
            log.exception("Handling commands failed.", exc_info=exc)
        log.debug(f"Reply {reply} to {sender} at node {s_node}.")
        if s_node == self.node:
            self.send_message_raw(sender_identity, receiver=sender,
                                  conversation_id=conversation_id, data=reply)
        else:
            self.send_message(receiver=sender, conversation_id=conversation_id, data=reply)

    def add_coordinator(self, host, port=12300, node=None):
        """Add another Coordinator to the connections.

        :param str host: Host name of address to connect to.
        :param int port: Port number to connect to.
        :param node: Namespace of the Node to add or 'None' for a temporary name.
        """
        if node is None:
            node = str(random()).encode()
        log.debug(f"Add DEALER for Coordinator {node} at {host}:{port}.")
        self.dealers[node] = d = self.context.socket(zmq.DEALER)
        d.connect(f"tcp://{host}:{port}")
        d.send_multipart(create_message(receiver=b"COORDINATOR", sender=self.fname,
                                        payload=serialize_data([[Commands.CO_SIGNIN,
                                                                 {'host': self.address[0],
                                                                  'port': self.address[1]}]])))
        self.node_addresses[node] = host, port
        self.waiting_dealers[node] = d

    def handle_dealer_message(self, sock, ns):
        """Handle a message at a DEALER socket.

        :param sock: DEALER socket.
        :param ns: Temporary name of that socket.
        """
        msg = sock.recv_multipart()
        try:
            version, receiver, sender, header, payload = divide_message(msg)
        except IndexError:
            log.error(f"Less than two frames received! {msg}.")
            return
        if deserialize_data(payload[0]) == [[Commands.ACKNOWLEDGE]]:
            s_node, s_name = split_name(sender)
            addr = self.node_addresses[ns]
            del self.dealers[ns]
            del self.waiting_dealers[ns]
            del self.node_addresses[ns]
            self.dealers[s_node] = sock
            # Rename address
            self.node_addresses[s_node] = addr
            log.info(f"Renaming DEALER socket from temporary {ns} to {s_node}.")
            self.send_message(receiver=sender, data=[self.compose_local_directory()])
        else:
            log.warning(f"Unknown message {payload} from {sender} at DEALER socket {ns}.")

    def compose_local_directory(self):
        """Send the local directory to the receiver."""
        return [Commands.SET,
                {'directory': [key.decode() for key in self.directory.keys()],
                 'nodes': {key.decode(): value for key, value in self.node_addresses.items()}}]


if __name__ == "__main__":
    if True or "-v" in sys.argv:  # Verbose log.
        log.setLevel(logging.DEBUG)
    if len(log.handlers) == 1:
        log.addHandler(logging.StreamHandler())
    kwargs = {}
    if "-h" in sys.argv:
        try:
            kwargs["host"] = sys.argv[sys.argv.index("-h") + 1]
        except IndexError:
            pass
    coordinators = []
    if "-c" in sys.argv:  # Coordinator hostname to connect to.
        try:
            coordinators.append([sys.argv[sys.argv.index("-c") + 1]])
        except IndexError:
            pass
    try:
        r = Coordinator(**kwargs)
        r.routing(coordinators)
    except KeyboardInterrupt:
        print("Stopped due to keyboard interrupt.")
