# pyleco

Python reference implementation of the Laboratory Experiment COntrol (LECO) protocol.

Prefer the project's virtual environment (e.g. `.venv/`) over global Python installations.

## Development Setup

```sh
pip install -e ".[dev]"
```

## Testing

```sh
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

## Project Structure

- `pyleco/core/` — Core LECO protocol: message, data_message, serialization, protocols
- `pyleco/utils/` — Communication utilities: communicator, message_handler, listener, data_publisher, rpc_handler
- `pyleco/actors/` — Device control actors (actor, locking_actor)
- `pyleco/directors/` — Remote control directors (director, transparent_director, coordinator_director, etc.)
- `pyleco/coordinators/` — LECO servers: coordinator (control protocol), proxy_server (data protocol)
- `pyleco/management/` — Starter, data_logger
- `pyleco/json_utils/` — JSON-RPC handling: rpc_generator, rpc_server, json_parser
