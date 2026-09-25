"""Shared pytest configuration."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register the markers used across the suite."""
    config.addinivalue_line(
        "markers",
        "live: calls the real Fabric API with credentials from the "
        "environment; CI runs these in a step that does not block the build",
    )
