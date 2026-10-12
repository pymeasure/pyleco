"""Pytest configuration for the integration tests directory.

Every test collected in this directory is automatically marked with the
``integration`` marker (registered in ``pyproject.toml``), so that the CI
workflow can select/exclude them via ``-m "not integration"`` /
``-m integration`` without per-file ``pytestmark`` declarations.

The path check makes this robust on both pytest<=8 (hook fires once per
directory scope) and pytest>=9 (hook fires once for the full session items).
"""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark every test collected under tests/integration_tests/ as integration."""
    for item in items:
        if "integration_tests" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
