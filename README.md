# PyLECO

Python reference implementation of the [Laboratory Experiment COntrol (LECO) protocol](https://github.com/pymeasure/leco-protocol).

The [reviewed branch](https://github.com/pymeasure/pyleco/tree/reviewed) contains reviewed code, which does not yet contain all necessary modules and classes.
Development happens in the [main](https://github.com/pymeasure/pyleco/tree/main) branch.

Note: LECO is still under development, such that the code and API might change.
The LECO protocol branch [pyleco-state](https://github.com/pymeasure/leco-protocol/tree/pyleco-state) contains the assumptions used in this project, which are not yet accepted into the LECO main branch.
These things might change, if LECO defines them differently.

[![codecov](https://codecov.io/gh/pymeasure/pyleco/graph/badge.svg?token=9OB3GWDLRB)](https://codecov.io/gh/pymeasure/pyleco)
[![pypi release](https://img.shields.io/pypi/v/pyleco.svg)](https://pypi.org/project/pyleco/)
[![Common Changelog](https://common-changelog.org/badge.svg)](https://common-changelog.org)

For a tutorial on how to get started, see [GETTING_STARTED.md](https://github.com/pymeasure/pyleco/blob/main/GETTING_STARTED.md).


## Quick Start

1. Install Python,
2. Execute `pip install pyleco`,
3. Import `pyleco` in your python scripts.


## LECO Overview

### Network Topology

PyLECO is an implementation of LECO, for the full protocol specifications please visit https://github.com/pymeasure/leco-protocol.
LECO offers a protocol for data exchange, for example for laboratory experimental control.

There exist two different communication protocols in LECO.
1. The control protocol allows to exchange messages between any two Components in a LECO network, which is useful for controlling devices.
2. The data protocol is a broadcasting protocol to send information to all those, who want to receive it, which is useful for regular measurement data or for log entries.

A LECO network needs at least one Coordinator (server), which routes the messages among the connected Components.

Each Component has a name unique in the network.
This name consists in the name of the Coordinator they are connected to and their own name.
For example `N1.component1` is the full name of `component1` connected to the Coordinator of the Namespace `N1`.
The Coordinator istelf is always called `COORDINATOR`.

### Remote Procedure Calls

The default messaging content of the control protocol are remote procedure calls (RPC) according to jsonrpc.
With these RPCs you execute a method on the remote Component.
For example you have an Actor, which is for example a Component controlling a measurement instrument.
In order to set the output of that measurement instrument, you want to call the `set_output` method of that instrument.
For that purpose, you send a message which encodes exactly that (via jsonrpc): the method to call and the parameters of that method.


## Usage of the Control Protocol

### Minimum Setup

For a minimum setup, you need:
* a Coordinator (just execute `coordinator` in your terminal or run the `coordinator.py` file with your Python interpreter)
* one Component

For example, you can use a `Communicator` instance to send/receive messages via LECO protocol.
The following example requests the list of Components connected to the Coordinator:

```python
from pyleco.utils.communicator import Communicator

c = Communicator(name="TestCommunicator")
connected_components = c.ask_rpc(method="send_local_components")
print(connected_components)
```

### Instrument Control

Let's say you have an instrument with a pymeasure driver `Driver`, which you want to control.

You need to start (in different threads):
* a Coordinator (as shown above).
* an `Actor` instance listening to commands and controlling the instrument: `actor = Actor(name="inst_actor", cls=Driver)`.
  For an example see the `pymeasure_actor.py` in the examples folder.
* a `TransparentDirector`: `director=TransparentDirector(actor="inst_actor")`. The `actor` parameter has to match the Actor's `name` parameter.
  For an example of a measurement script see `measurement_script.py` in the examples folder.

If you want to set some property of the instrument (e.g. `instrument.voltage = 5`), you can just use the `director` transparently: `director.device.voltage = 5`.
In the background, the TransparentDirector, which does not have a `device`, sends a message to the Actor to set that parameter.
The Actor in turn sets that parameter of the instrument driver, which in turn will send some command to the device to take an appropriate action (e.g. setting the voltage to 5 V).

Currently you cannot call methods in a similar, transparent way, without manual intervention.
You can add `RemoteCall` descriptor (in transparent_director module) to the `director` for each method call you want to use.
Afterwards you can use these methods transparently similar to the property shown above.


## Overview of Offered Packages and Modules

See the docstrings of the individual classes for more information and for examples.

* The `core` subpackage contains elements necessary for implementing LECO, especially the `Message` class, which helps to create and interpret LECO messages.
* The `utils` subpackage contains modules useful for creating LECO Components.
  * The`Communicator` can send and receive messages, but neither blocks (just for a short time waiting for an answer) nor requires an extra thread.
    It is useful for usage in scripts.
  * The `MessageHandler` handles incoming messages in a continuous loop (blocking until stopped).
    It is useful for creating standalone scripts, like tasks for the Starter.
  * The `Listener` offers the same interface as the Communicator, but listens in an extra thread for incoming messages.
    It is useful if you want to react to incoming messages (via data or control protocol) and if you want to send messages of your own accord, for example for GUI applications.
* The `coordinators` subpackage contains the differenc Coordinators.
  * `Coordinator` is the Coordinator for the control protocol (exchanging messages).
  * `proxy_server` is the Coordinator for the data protocol (broadcasting).
* The `actors` subpackage contains Actor classes to control devices.
* The `management` subpackage contains Components useful for experiment management
  * The `Starter` can execute tasks in separate threads.
    A task could be an Actor controlling some Device.
  * The `DataLogger` listens to published data (data protocol) and collects them.
* The `directors` subpackage contains Directors, which facilitate controlling actors or management utilities.
  * For example the `CoordinatorDirector` has a method for getting Coordinators and Components connected to a Coordinator.
  * The `TransparentDirector` reads / writes all messages to the remote actor, such that you use the director's `device` as if it were the instrument itself.

### PyLECO extras

The [pyleco-extras](https://github.com/BenediktBurger/pyleco-extras) package contains additional modules.
Among them are GUIs controlling the `DataLogger` and the `Starter`.
