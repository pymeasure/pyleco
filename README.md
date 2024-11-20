# PyLECO

![PyPI - Python Version](https://img.shields.io/pypi/pyversions/pyleco)
[![codecov](https://codecov.io/gh/pymeasure/pyleco/graph/badge.svg?token=9OB3GWDLRB)](https://codecov.io/gh/pymeasure/pyleco)
[![pypi release](https://img.shields.io/pypi/v/pyleco.svg)](https://pypi.org/project/pyleco/)
[![conda-forge release](https://anaconda.org/conda-forge/pyleco/badges/version.svg)](https://anaconda.org/conda-forge/pyleco)
[![DOI](https://zenodo.org/badge/594982645.svg)](https://zenodo.org/doi/10.5281/zenodo.10837366)
[![Common Changelog](https://common-changelog.org/badge.svg)](https://common-changelog.org)

Python reference implementation of the [Laboratory Experiment COntrol (LECO) protocol](https://github.com/pymeasure/leco-protocol).

**Note**: LECO is still under development, such that the code and API might change.
The LECO protocol branch [pyleco-state](https://github.com/pymeasure/leco-protocol/tree/pyleco-state) contains the assumptions used in this project, which are not yet accepted into the LECO main branch.
See this [documentation](https://leco-laboratory-experiment-control-protocol--69.org.readthedocs.build/en/69/) for the LECO definitions including these assumptions.
These things might change, if LECO defines them differently.

For a tutorial on how to get started, see [GETTING_STARTED.md](https://github.com/pymeasure/pyleco/blob/main/GETTING_STARTED.md).

You are welcome to contribute, for more information see [CONTRIBUTING.md](https://github.com/pymeasure/pyleco/blob/main/CONTRIBUTING.md).


## Quick Start

1. Install Python,
2. install PyLECO with `pip install pyleco` or `conda install conda-forge::pyleco`,
3. import the package `pyleco` in your python scripts,
4. and use it as desired.


## LECO Overview

### Network Topology

PyLECO is an implementation of LECO, for the full protocol specifications please visit https://github.com/pymeasure/leco-protocol.
LECO offers a protocol for data exchange, for example for laboratory experimental control.

There exist two different communication protocols in LECO.
1. The control protocol allows to exchange messages between any two _Components_ in a LECO network, which is useful for controlling devices.
2. The data protocol is a broadcasting protocol to send information to all those, who want to receive it, which is useful for regular measurement data or for log entries.

A LECO network needs at least one _Coordinator_ (server), which routes the messages among the connected Components.

Each _Component_ has a name unique in the network.
This name consists in the name of the _Coordinator_ they are connected to and their own name.
For example `N1.component1` is the full name of `component1` connected to the _Coordinator_ of the _Namespace_ `N1`.
That _Coordinator_ itself is called `N1.COORDINATOR`, as _Coordinators_ are always called `COORDINATOR`.

### Remote Procedure Calls

The default messaging content of the control protocol are _remote procedure calls_ (RPC) according to [JSON-RPC](https://www.jsonrpc.org/specification).
RPC means, that you execute a method (or procedure) on a remote _Component_.
For example you have an Actor, which is for example a Component controlling a measurement instrument.
In order to set the output of that measurement instrument, you want to call the `set_output` method of that instrument.
For that purpose, you send a message which encodes exactly that (via jsonrpc): the method to call and the parameters of that method.


## Usage of the Control Protocol

### Minimum Setup

For a minimum setup, you need:
* a _Coordinator_ (just execute `coordinator` in your terminal or run the `coordinator.py` file with your Python interpreter),
* one _Component_.

For example, you can use a `Communicator` instance to send/receive messages via LECO protocol.
The following example requests the list of _Components_ connected currently to the _Coordinator_:

```python
from pyleco.utils.communicator import Communicator

c = Communicator(name="TestCommunicator")
connected_components = c.ask_rpc(method="send_local_components")
print(connected_components)
```

### Instrument Control

Let's say you have an instrument with a pymeasure driver `Driver`, which you want to control.

You need to start (in different threads):
* a _Coordinator_ (as described above),
* an `Actor` instance listening to commands and controlling the instrument: `actor = Actor(name="inst_actor", cls=Driver)`.
  For an example see the `pymeasure_actor.py` in the examples folder,
* a `TransparentDirector`: `director=TransparentDirector(actor="inst_actor")`. The `actor` parameter has to match the Actor's `name` parameter.
  For an example of a measurement script see `measurement_script.py` in the examples folder.

If you want to set some property of the instrument (e.g. `instrument.voltage = 5`), you can just use the `director` transparently: `director.device.voltage = 5`.
In the background, the TransparentDirector, which does not have a `device`, sends a message to the Actor to set that parameter.
The Actor in turn sets that parameter of the instrument driver, which in turn will send some command to the device to take an appropriate action (e.g. setting the voltage to 5 V).

Currently you cannot call methods in a similar, transparent way, without manual intervention.
You can add `RemoteCall` descriptor (in transparent_director module) to the `director` for each method call you want to use.
Afterwards you can use these methods transparently similar to the property shown above.


## Overview of Offered Packages and Modules

PyLECO offers the following subpackages and modules.
For more information and for examples see the docstrings of the relevant methods and classes.

* The `core` subpackage contains elements necessary for implementing LECO and for interacting with PyLECO, for example:
  * The `Message` and `DataMessage` class help to create and interpret LECO messages for the control and broadcasting protocol, respectively.
  * The `leco_protocols` module contains _Protocol_ classes for the different LECO _Components_, in order to test, whether a _Component_ satisfies the LECO standard for communicating with other programs.
  * The `internal_protocols` module contains _Protocol_ classes which define the API access to PyLECO.
* The `utils` subpackage contains modules useful for creating LECO Components.
  * The`Communicator` can send and receive messages, but neither blocks (just for a short time waiting for an answer) nor requires an extra thread.
    It satisfies the `CommunicatorProtocol` and is useful in scripts.
  * The `MessageHandler` also satisfies the `CommunicatorProtocol`, but handles incoming messages in a continuous loop (blocking until stopped).
    It is useful for creating standalone scripts, like tasks for the _Starter_.
  * The `ExtendedMessageHandler` adds the capability to subscribe and receive data protocol messages.
  * The `Listener` offers an interface according to the `CommunicatorProtocol`, but listens at the same time in an extra thread for incoming messages (with an `ExtendedMessageHandler`).
    It is useful if you want to react to incoming messages (via data or control protocol) and if you want to send messages of your own accord, for example for GUI applications.
* The `coordinators` subpackage contains the different _Coordinators_.
  * `Coordinator` is the _Coordinator_ for the control protocol (exchanging messages).
  * `proxy_server` is the _Coordinator_ for the data protocol (broadcasting).
* The `actors` subpackage contains _Actor_ classes to control devices.
* The `management` subpackage contains _Components_ useful for experiment management.
  * The `Starter` can execute tasks in separate threads.
    A task could be an _Actor_ controlling some _Device_.
  * The `DataLogger` listens to published data (via the data protocol) and collects them.
* The `directors` subpackage contains Directors, which facilitate controlling actors or management utilities.
  * The `Director` is a base _Director_.
    It can communicate via any util, which implements the `CommunicatorProtocol`.
  * For example the `CoordinatorDirector` has a method for getting _Coordinators_ and _Components_ connected to a _Coordinator_.
  * The `TransparentDirector` reads / writes all messages to the remote actor, such that you use the director's `device` as if it were the instrument itself.

### PyLECO extras

The [pyleco-extras](https://github.com/BenediktBurger/pyleco-extras) package contains additional modules.
Among them are GUIs controlling the `DataLogger` and the `Starter`.
