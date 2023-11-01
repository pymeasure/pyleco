# Assumptions of LECO

LECO is not yet fully defined, but some features are required for the code to work.
Here are internal definitions used for PyLECO, which are not yet in LECO, so they might change.

The assumptions link to issues/pull requests, where these points are discussed.

## Control Protocol

### Control Protocol Message

The header frame consists of three parts:
1. UUIDv7 as conversation_id
2. 3 bytes as message_id, the content (whether a timestamp or a count) is not yet defined.
3. 1 byte as message_type which contains the serialization scheme:
   - 0 means not defined,
   - 1 means JSON, our default

### Message content

Messages use JSONRPC messages.
Also the control messages (sign_in etc.) are done via JSONRPC.
Error codes are also defined.
All this is in [PR #56](https://github.com/pymeasure/leco-protocol/pull/56) defined.
Some assumptions of that content:
* Get/set_parameters and call_action refers to the Actor's device only (see definition of Actor)
* Parameters/actions of channels are indicated by a period (e.g. `ch_A.par1` will call the parameter `par1` of channel `ch_A`)


### Coordinator Workings

#### Directory update at sign-in/sign-out

At each sign-in/sign-out of a Component, the Coordinator sends the full directory (components/Coordinators) to all known Coordinators.

If a not signed in Coordinator tries to sign out, the Coordinator ignores that message.

If a Coordinator tries to sign out, but the message arrives via a different identity, the sign-out is rejected.


## Data Protocol

### Message Format

A Data Protocol Message consists in three or more frames ([#62](https://github.com/pymeasure/leco-protocol/issues/62)):
1. Topic (see below)
2. Header (see below)
3. One or more data frames

#### Topic

The topic is the full name of the sending Component. ([#60](https://github.com/pymeasure/leco-protocol/issues/60))

#### Header

Similar to the control protocol ([#61](https://github.com/pymeasure/leco-protocol/issues/61)):
1. UUIDv7
2. 1 byte Message_type (0 not defined, 1 JSON, >127 user defined)

#### Content

For log messages, the content is a list of:
- record.asctime: Timestamp formatted as '%Y-%m-%d %H:%M:%S'
- record.levelname: Logger level name
- record.name: Logger name
- record text (including traceback)


## General

As default ports for the different applications:

- COORDINATOR_PORT = 12300  # the Coordinator receives and sends at that port.
- PROXY_RECEIVING_PORT = 11100  # the proxy server receives at that port
- PROXY_SENDING_PORT = 11099  # the proxy server sends at that port
- LOG_RECEIVING_PORT = 11098  # the log server receives at that port
- LOG_SENDING_PORT = 11097  # the log server sends at that port
