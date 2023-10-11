# PyLECO
Python reference implementation of the Laboratory Experiment COntrol (LECO) protocol (https://github.com/pymeasure/leco-protocol).


## Installation

For now, as PyLECO is not yet a PyPI / conda package, you have to clone this repository and install it manually.
Eventually it will be published as `pyleco`.
Execute `pip install` in this folder for installation.

It is recommended to install them editable.
That way, a file import will redirect to the files in this directory, however they will be at import time.
That allows to update PyLECO by just pulling the latest master branch, or to develop for PyLECO.
In order to do an editable install, execute `pip install -e .` in this folder.


## Overview

### Network Topology

PyLECO is an implementation of LECO, so see there for exact protocol specifications.
LECO offers a protocol for data exchange, for example for laboratory experimental control.

There exist two different communication styles.
The first communication style broadcasts information to all those, who want to receive it, which is useful for regular measurement data or for log entries.
The other communication style exchanges messages between any two Components in a LECO network, which is useful for controlling devices.

A LECO network needs at least one Coordinator (server), which routes the messages among the connected Components.

Each Component has a name unique in the network.
This name consists in the name of the Coordinator they are connected to and their own name.
For example `N1.component1` is the full name of `component1` connected to the Coordinator of the Namespace `N1`.
The Coordinator istelf is always called `COORDINATOR`.

### Remote Procedure Calls

The default messaging content are remote procedure calls (RPC) according to jsonrpc.
So you call a message of the receiver.


## Minimum Setup

For a minimum setup, you need:
* a Coordinator (just run `coordinator.py`)
* one Component

For example, you can use a `Communicator` instance to send/receive messages via LECO protocol.
The following example requests the list of Components connected to the Coordinator:

```python
from pyleco.utils.communicator import Communicator

c = Communicator(name="TestCommunicator")
connected_components = c.ask_rpc(method="send_local_components")
print(connected_components)
```


## Overview of Offered Packages and Modules

* The `core` subpackage contains elements necessary for implementing LECO, especially the `Message` class, which helps to setup and interpret LECO messages
* The `utils` subpackage contains modules useful for creating LECO Components.
  * The`Communicator` can send and receive messages, but neither blocks nor requires an extra thread.
    It is useful for usage in scripts.
  * The `MessageHandler` handles incomming messages in a continuous loop.
    It is useful for creating standalone scripts, like tasks for the Starter.
  * The `Listener` offers the same interface as the Communicator, but listens in an extra thread for incoming messages.
    It is useful if you want to react to incoming messages (via data or control protocol) and if you want send messages of your own accord, for example for GUI applications.
* The `coordinators` subpackage contains the differenc Coordinators.
  * `Coordinator` is the Coordinator for the control protocol (exchanging messages).
  * `proxy_server` is the Coordinator for the data protocol (broadcasting).
* The `actors` subpackage contains Actor classes to control devices.
* The `management` subpackage contains Components useful for experiment management
  * The `Starter` can execute tasks in separate threads, for example one task per device
  * The `DataLogger` listens to published data (data protocol) and collects them
* The `directors` subpackage contains Directors, which facilitate controlling actors or management utilities.
  For example the `CoordinatorDirector` has a method for getting Coordinators and Components connected to a Coordinator.
