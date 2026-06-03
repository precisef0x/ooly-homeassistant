"""Shared fixtures for the OOLY integration tests."""

from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

# Pre-spawn the aiodns/pycares resolver's daemon thread at import time. Otherwise the first
# test that creates an aiohttp client session spawns it mid-test, and the strict teardown
# cleanup in pytest-homeassistant-custom-component flags it as a "leaked" thread.
try:
    import pycares

    _RESOLVER_WARMUP = pycares.Channel()
except Exception:  # pragma: no cover - pycares may be unavailable
    _RESOLVER_WARMUP = None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load the `ooly` custom integration in tests."""
    yield
