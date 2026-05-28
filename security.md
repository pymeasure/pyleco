# Security

LECO controls physical laboratory hardware, where unauthorized or tampered commands can damage equipment or cause safety hazards.
This section defines the security mechanisms available to protect LECO networks.

## Security modes

A LECO Network operates in one of the following security modes:

| Mode    | Authentication   | Encryption        | Use case                                 |
|---------|------------------|-------------------|------------------------------------------|
| `NONE`  | No               | No                | Local development, trusted networks only |
| `CURVE` | Yes (Curve25519) | Yes (per-session) | Production deployments (RECOMMENDED)     |

All Nodes in a Network MUST use the same security mode.
A Coordinator SHALL reject connections that use a different security mode than its own.

Each Component determines its security mode from its local configuration (e.g., a configuration file, command-line argument, or environment variable), alongside other connection parameters such as the Coordinator's host and port.
A Component SHALL NOT attempt to autodetect the security mode by trying `CURVE` and falling back to `NONE`, as this is vulnerable to downgrade attacks.

Implementations MUST support the `NONE` mode and SHOULD support the `CURVE` mode.

:::{warning}
The `NONE` mode provides no security.
It MUST NOT be used on networks accessible to untrusted parties.
Any ZeroMQ client can connect, sign in with any name, and send commands to any Component.
:::

## CURVE security mode

The `CURVE` mode uses [CurveZMQ](https://rfc.zeromq.org/spec/50/) (RFC 50) to provide mutual authentication and encryption at the ZeroMQ transport layer.
It requires [libsodium](https://doc.libsodium.org/) and libzmq >= 4.0 (bundled with pyzmq >= 14.0).

CurveZMQ authenticates connections before any LECO message is exchanged.
The LECO message format and protocol flows remain unchanged.

### Cryptographic keys

Each entity in a `CURVE`-secured Network has a long-term Curve25519 key pair:

- **Server key pair**: Each Coordinator has a server key pair (`server_secret_key`, `server_public_key`).
  The ROUTER socket uses the server secret key.
- **Client key pair**: Each Component (including Coordinators connecting as clients to other Coordinators) has a client key pair (`client_secret_key`, `client_public_key`).
  The DEALER/PUBLISHER/SUBSCRIBER socket uses the client secret key.

Key pairs SHOULD be generated using the ZMQ curve key generation utilities (e.g. `zmq.curve_keypair()` in pyzmq).

### Key distribution

A Coordinator SHALL maintain a list of authorized client public keys.

The mechanism for populating this list is implementation-defined.
RECOMMENDED approaches include:

1. **Key directory**: The Coordinator reads authorized public keys from a directory on the filesystem (one key per file, similar to SSH `authorized_keys`).
   File names SHOULD correspond to the intended Component name for traceability.
2. **Configuration file**: The Coordinator reads authorized public keys from a configuration file mapping Component names to public keys.
3. **Any-authenticated mode**: The Coordinator accepts any client with a valid CurveZMQ handshake, without checking the public key against a list.
   This provides encryption and prevents unauthenticated outsiders from connecting, but does not restrict which authenticated Components may join.

Implementations SHOULD support option 1 or 2 for production use, and MAY support option 3 for simplified setups.

Client public keys MUST NOT be transmitted over the network as part of the LECO protocol.
They MUST be distributed out-of-band (e.g., copied via secure file transfer, shared on a USB drive, or provisioned by a deployment tool).

### Control protocol setup

In `CURVE` mode, the control channel is secured as follows:

**Coordinator (server side):**

1. Set `CURVE_SERVER = 1` on the ROUTER socket.
2. Set `CURVE_SECRETKEY` to the server's secret key.
3. Optionally configure a ZAP handler to validate client public keys against the authorized list.

**Component (client side):**

1. Set `CURVE_SERVERKEY` to the Coordinator's server public key.
2. Set `CURVE_PUBLICKEY` and `CURVE_SECRETKEY` to the Component's own key pair.
3. Connect the DEALER socket to the Coordinator's ROUTER socket.

Both the Coordinator's security mode and the Component's security mode are determined by their respective local configurations.
They MUST agree; if they do not, the ZMQ connection will fail:

- A `CURVE` Component connecting to a `NONE` Coordinator will fail the CurveZMQ handshake (the Coordinator does not speak the Curve protocol).
- A `NONE` Component connecting to a `CURVE` Coordinator will be rejected because it does not complete the CurveZMQ handshake.

In either case, the connection is simply never established — no LECO messages are exchanged and no ambiguous error arises.

After the CurveZMQ handshake completes, the normal LECO `sign_in` flow proceeds unchanged.

If the CurveZMQ handshake fails (wrong server key, unauthorized client key), the connection is rejected at the ZMQ transport layer.
The Coordinator SHALL log the rejection reason (from ZAP) to aid debugging.
No LECO-level error message is sent because the connection is never established.

:::{mermaid}
sequenceDiagram
    participant CA as Component A
    participant Co as N1.COORDINATOR
    Note over CA,Co: CURVE mode handshake
    CA ->> Co: ZMQ CURVE handshake (client_secret + server_public)
    Note right of Co: ZAP validates client public key
    alt Handshake succeeds
        Co -->> CA: Handshake OK
        CA ->> Co: V|COORDINATOR|CA|H|sign_in
        Co ->> CA: V|N1.CA|N1.COORDINATOR|H|result
    else Unauthorized key
        Co -->> CA: Connection rejected (ZAP)
        Note right of Co: Log: "CURVE auth failed for [key hash]"
    else Wrong server key
        CA -->> Co: Handshake fails
        Note left of CA: Log: "CURVE handshake failed"
    end
:::

### Coordinator-to-Coordinator setup

When two Coordinators connect in `CURVE` mode:

- The connecting Coordinator acts as a client (DEALER socket), using its own client key pair and the remote Coordinator's server public key.
- The receiving Coordinator acts as a server (ROUTER socket), as described above.
- Both directions of the bidirectional link are secured independently.

### Data protocol setup

The data protocol (XPUB/XSUB proxy) uses CurveZMQ in a relay configuration:

**Proxy server (Data Coordinator):**

1. Set `CURVE_SERVER = 1` on the XPUB socket.
2. Set `CURVE_SECRETKEY` to the proxy's server secret key.
3. Set `CURVE_SERVER = 1` on the XSUB socket.
4. Set `CURVE_SECRETKEY` to the same (or a different) server secret key.

**Publisher (client side):**

1. Set `CURVE_SERVERKEY` to the proxy's XSUB server public key.
2. Set `CURVE_PUBLICKEY` and `CURVE_SECRETKEY` to the Publisher's own key pair.
3. Connect the PUB socket to the proxy's XSUB socket.

**Subscriber (client side):**

1. Set `CURVE_SERVERKEY` to the proxy's XPUB server public key.
2. Set `CURVE_PUBLICKEY` and `CURVE_SECRETKEY` to the Subscriber's own key pair.
3. Connect the SUB socket to the proxy's XPUB socket.

For the logging coordinator, the same pattern applies.

:::{note}
In CurveZMQ's PUB/SUB pattern, only the SUB/PUB client authenticates to the server.
The server does not authenticate to the client by default.
To achieve mutual authentication for the data channel, implementations SHOULD use a ZAP handler on the proxy to validate client public keys.
:::

## Upgrade considerations

### From NONE to CURVE

Existing deployments operating in `NONE` mode can upgrade to `CURVE` mode with the following steps:

1. **Generate key pairs**: Generate a server key pair for each Coordinator, and a client key pair for each Component.
2. **Distribute server public keys**: Each Component needs the server public key of its Coordinator.
3. **Distribute authorized client public keys**: Each Coordinator needs the public keys of all Components that should be allowed to connect.
4. **Enable CURVE mode on all entities**: Update the configuration of each Coordinator and Component.
5. **Restart the entire Network**: Since security mode must be uniform, all Nodes must switch simultaneously.

:::{warning}
A Network with mixed security modes will fail:
a Component in `NONE` mode cannot connect to a Coordinator in `CURVE` mode (and vice versa).
Plan a coordinated upgrade.
:::

### Protocol version

The LECO protocol version field (frame 1 of every message) remains unchanged when security mode changes.
Security negotiation happens entirely at the ZMQ transport layer and does not affect the LECO message format.

### Implementation compatibility

Implementations that do not support `CURVE` mode will not be able to connect to `CURVE`-secured Networks.
Implementations SHOULD:

- Clearly indicate whether they support `CURVE` mode in their documentation.
- Provide a meaningful error message if a `CURVE` handshake fails (e.g., "CURVE authentication failed: ensure the server key and client key are correctly configured").
- Default to `NONE` mode for backward compatibility, but emit a warning if `NONE` mode is used on a non-loopback network interface.

## Threat model

The security mechanisms in this section address the following threats:

| Threat                                                          | Mitigation                                                             | Mode    |
|-----------------------------------------------------------------|------------------------------------------------------------------------|---------|
| Unauthorized Component connecting to a Coordinator              | Client public key authentication                                       | `CURVE` |
| Network eavesdropping on control or data messages               | Per-session encryption                                                 | `CURVE` |
| Message tampering or injection in transit                       | Encryption with integrity checks (built into CurveZMQ)                 | `CURVE` |
| Name spoofing (Component claiming another's name)               | Coordinator maps authenticated public key to authorized Component name | `CURVE` |
| Accidental misconnection (wrong Component to wrong Coordinator) | Server key ensures Components connect to the intended Coordinator      | `CURVE` |

### Out of scope

The following threats are NOT addressed by the current security mechanisms:

- **Authorization / access control**: Once authenticated, any Component can send any RPC method to any other Component.
  Future versions MAY define an access control mechanism.
- **Compromised keys**: If a Component's secret key is leaked, an attacker can impersonate it.
  Key rotation is the responsibility of the deployment.
- **Denial of service**: An attacker with network access can flood a Coordinator with connection attempts.
  Rate limiting and network-level protections are out of scope.
- **Local privilege escalation**: Components running on the same machine may be able to read each other's key files.
  File permissions and OS-level security are out of scope.
