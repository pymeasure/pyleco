# PyLECO Project Context

## Project Overview

PyLECO is a Python reference implementation of the Laboratory Experiment COntrol (LECO) protocol.
It provides a distributed messaging system for controlling laboratory equipment and collecting experimental data.
The system is designed around a network topology with multiple components communicating through coordinators.

### Core Concepts

1. **Network Topology**:
   - LECO networks consist of Components connected to Coordinators
   - Each Component has a unique name in the format `Namespace.ComponentName`
   - Coordinators route messages between Components within and across namespaces
   - Two communication protocols: control protocol (point-to-point) and data protocol (broadcasting)

2. **Remote Procedure Calls (RPC)**:
   - Default messaging uses JSON-RPC for remote method calls
   - Components can expose methods that can be called remotely
   - TransparentDirector allows property-style access to remote components

3. **Key Components**:
   - **Coordinator**: Routes messages between components (control protocol)
   - **Proxy Server**: Handles data broadcasting (data protocol)
   - **Actor**: Controls physical devices/instruments
   - **Director**: Controls other components (especially Actors)
   - **Starter**: Manages execution of multiple tasks in separate threads
   - **DataLogger**: Collects and stores published data

## Project Structure

```
pyleco/
├── actors/           # Actor implementations for device control
├── coordinators/     # Coordinator and proxy server implementations
├── core/             # Core messaging and protocol implementations
├── directors/        # Director classes for controlling components
├── json_utils/       # JSON-RPC utilities and error handling
├── management/       # Management utilities (Starter, DataLogger)
├── utils/            # Utility classes and helpers
├── __init__.py       # Package initialization and version info
├── errors.py         # Legacy error definitions
└── test.py           # Testing utilities with fake ZMQ objects

tests/
├── core/             # Unit tests for core components
├── actors/           # Unit tests for actors
├── coordinators/     # Unit tests for coordinators
├── directors/        # Unit tests for directors
├── management/       # Unit tests for management components
├── utils/            # Unit tests for utilities
└── integration_tests/ # Integration tests

examples/
├── pymeasure_actor.py     # Example actor implementation
└── measurement_script.py  # Example director usage

docs/                   # Sphinx documentation
```

## Key Classes and Modules

### Core Messaging

- `pyleco.core.message.Message`: Main message class with frames (version, receiver, sender, header, payload)
- `pyleco.core.serialization`: Serialization utilities for converting between Python objects and bytes

### Communication Utilities

- `pyleco.utils.communicator.Communicator`: Simple communicator for sending requests and reading responses
- `pyleco.utils.message_handler.MessageHandler`: Base class for components that listen for messages continuously
- `pyleco.utils.extended_message_handler.ExtendedMessageHandler`: Message handler with data protocol subscription support
- `pyleco.utils.listener.Listener`: Runs message handler in separate thread with exposed communicator

### Component Types

- `pyleco.actors.actor.Actor`: Controls devices, inherits from MessageHandler
- `pyleco.directors.director.Director`: Base class for directing other components
- `pyleco.directors.transparent_director.TransparentDirector`: Provides transparent access to remote component properties
- `pyleco.management.starter.Starter`: Starts and manages tasks in separate threads
- `pyleco.management.data_logger.DataLogger`: Collects and stores published data
- `pyleco.coordinators.coordinator.Coordinator`: Routes messages between components
- `pyleco.coordinators.proxy_server.ProxyServer`: Broadcasts data messages

## Building and Running

Prefer the project's virtual environment (e.g. `.venv/`) over global Python installations.

### Installation

```bash
# Install from PyPI
pip install pyleco

# Or install from conda-forge
conda install conda-forge::pyleco
```

### Running Components

PyLECO provides command-line scripts for the main components:

```bash
# Start a coordinator
coordinator [--port PORT] [--namespace NAMESPACE] [--coordinators COORD_LIST]

# Start a proxy server (data protocol coordinator)
proxy_server [--port PORT]

# Start a task starter
starter [--directory DIR] [TASK_NAMES...]
```

### Basic Usage Pattern

1. Start a Coordinator: `coordinator`
2. Start a Proxy Server: `proxy_server`
3. Create and start Actors to control devices
4. Use Directors to control Actors
5. Use DataLogger to collect published data

Example:

```python
# In one terminal
coordinator

# In another terminal
from pyleco.utils.communicator import Communicator
c = Communicator(name="TestCommunicator")
connected_components = c.ask_rpc(method="send_local_components")
print(connected_components)
```

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Or with conda
conda env update -f environment.yml
```

## Testing

PyLECO uses pytest for testing with the following structure:

- Unit tests in `tests/` directory mirroring the source structure
- Integration tests in `tests/integration_tests/`
- Test utilities in `pyleco.test` providing fake ZMQ objects

Run tests with:

```bash
pytest
pytest --cov
```

Tests mirror the source structure: `pyleco/core/message.py` → `tests/core/test_message.py`.
Integration tests are in `tests/integration_tests/`.

The module `pyleco/test.py` provides fake ZMQ classes (FakeContext, FakeSocket, FakeCommunicator, FakeDirector) for unit testing without a real ZMQ connection.

## Linting & Type Checking

```sh
ruff check .
ruff format .
mypy .
```

Config is in `pyproject.toml`: line-length 100, ruff rules E/F/W/FURB/UP, mypy strict mode.

## Development Conventions

1. **Python Support**: Python 3.8+
2. **Documentation**: Minimal docstrings - only when method name is insufficient
3. **Testing**: Test-driven development encouraged
4. **Code Style**: Follows standard Python conventions with black/isort/ruff for formatting
5. **Dependencies**: Keep minimal, use optional dependencies where appropriate

## Key Patterns

### Actor Pattern

Actors control devices and can publish data periodically:

```python
from pyleco.actors.actor import Actor

with Actor(name="device_actor", device_class=DeviceClass) as actor:
    actor.connect(adapter_address)
    actor.listen(stop_event)
```

### Director Pattern

Directors control other components, with TransparentDirector providing property-style access:

```python
from pyleco.directors.transparent_director import TransparentDirector

director = TransparentDirector(actor="namespace.device_actor")
director.device.property = value  # Sets remote property
current_value = director.device.property  # Gets remote property
```

### Message Handler Pattern

For components that need to listen continuously:

```python
from pyleco.utils.message_handler import MessageHandler

handler = MessageHandler("component_name")
handler.register_rpc_method(some_method)
handler.listen()
```

## Configuration

Configuration is handled through:

- `pyproject.toml`: Project metadata, dependencies, build system
- `environment.yml`: Conda environment specification
- Command-line arguments for runtime configuration
- Optional TOML config file (`pyleco.toml`) for security settings

## Security (CURVE mode)

LECO supports two security modes: `NONE` (default, no encryption) and `CURVE` (CurveZMQ mutual authentication + encryption).

### Security configuration

Security is configured via `pyleco.core.security.SecurityConfig`, loaded from CLI args and/or a TOML config file:

```toml
[security]
mode = "CURVE"
server_secret_key = "..."   # Coordinator/Proxy server secret key
server_public_key = "..."   # Server public key (also used by clients)
client_public_key = "..."   # Component client public key
client_secret_key = "..."   # Component client secret key
data_server_public_key = "..."  # Proxy's server public key for data protocol
authorized_keys_dir = "/etc/pyleco/keys"  # Directory of authorized client public keys
curve_any_authenticated = false

[security.authorized_keys]  # Inline name→public_key mapping
"N1.Actor1" = "..."
```

### Key classes/modules

- `pyleco.core.security`: `SecurityMode` enum, `KeyPair`, `SecurityConfig`, `generate_key_pair()`, `load_authorized_keys()`, `load_security_config()`
- `pyleco.core.curve`: `configure_curve_server()`, `configure_curve_client()`, `configure_socket_security()` — apply CURVE socket options
- `pyleco.core.zap`: `start_authenticator()`, `stop_authenticator()` — manage ZMQ ZAP authenticator for client key validation
- `pyleco.core.config`: `load_config()` — TOML config file loading

### Key distribution

Three approaches for Coordinator-side authorized client keys:
1. **Key directory**: Files in `authorized_keys_dir`, one public key per file, filename = component name
2. **Config file**: `[security.authorized_keys]` table in TOML config
3. **Any-authenticated mode**: `curve_any_authenticated = true` accepts any valid CurveZMQ handshake

### CURVE socket setup

- **Coordinator ROUTER**: `configure_curve_server()` with server key pair
- **Component DEALER**: `configure_curve_client()` with client key pair + coordinator server public key
- **Proxy XPUB/XSUB**: `configure_curve_server()` with proxy server key pair
- **Publisher PUB**: `configure_curve_client()` with client key pair + proxy XSUB server public key
- **Subscriber SUB**: `configure_curve_client()` with client key pair + proxy XPUB server public key

### Key generation

Use `generate_key_pair()` or the `pyleco-keygen` CLI tool to generate Curve25519 key pairs.

## Development Environment

- Python 3.12 with built-in `tomllib` (no `tomli` needed)

### Venv usage

The `.venv/` directory was created on the host system and contains native extensions (e.g. pyzmq) linked against the host's glibc. These binaries fail inside Docker containers with errors like `ImportError: Error loading shared library ld-linux-x86-64.so.2`.

**If running in a Docker container**, use `.venv-docker/` instead:

```bash
.venv-docker/bin/pip3 install ...
.venv-docker/bin/pytest
.venv-docker/bin/python3 ...
```

**If running on the host**, use `.venv/` as before:

```bash
.venv/bin/pip3 install ...
.venv/bin/pytest
.venv/bin/python3 ...
```

The `.venv-docker/` should be excluded from version control (already covered by a generic `.venv` gitignore pattern; add `.venv-docker/` if needed).

### Running tests in a Docker container

The `.venv-docker/` venv has working pyzmq but two quirks:

1. **Shebang issue**: `pip3` and `pytest` scripts have a stale shebang pointing to `.docker-venv/bin/python3`. Use `python3 -m` instead:

   ```bash
   .venv-docker/bin/python3 -m pip install ...
   .venv-docker/bin/python3 -m pytest
   ```

2. **Project not installed**: `pip install -e .` fails because the container has no internet access (proxy blocks PyPI, and direct connections also fail). Set `PYTHONPATH` instead:

   ```bash
   PYTHONPATH=/home/benediktb/Repositories/pyleco .venv-docker/bin/python3 -m pytest
   ```

3. **Known flaky tests**: Two tests use `caplog` and intermittently fail with `IndexError` due to log record timing:
   - `tests/utils/test_extended_message_handler.py::test_subscribe_single_again`
   - `tests/utils/test_message_handler.py::Test_finish_sign_in::test_log_message`
   These are pre-existing and unrelated to security changes. They pass when run individually.

## Common Tasks

### Adding a New RPC Method

1. Create a method in your component class
2. Register it with `register_rpc_method(method)`
3. It will be available for remote calls via `ask_rpc(method="method_name")`

### Creating a Custom Actor

1. Inherit from `pyleco.actors.actor.Actor`
2. Implement `read_publish` method for periodic data publishing
3. Optionally override other methods as needed

### Setting Up Multi-Computer Networks

1. Start coordinators on each computer with different ports if needed
2. Connect coordinators using `--coordinators` argument or `add_nodes` RPC method
3. Components connect to their local coordinator
4. Messages automatically route between coordinators
