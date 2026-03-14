"""pytest configuration and shared fixtures for Fingerprint Manager tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.fingerprint_manager.const import (
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_TYPE,
    CONF_SENSOR_ENTITY,
    DEFAULT_EVENT_TYPE,
    DOMAIN,
    FINGERPRINT_STORAGE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_config_entry(
    data: dict | None = None,
    options: dict | None = None,
    entry_id: str = "test_entry_id",
) -> MagicMock:
    """Return a minimal mock ConfigEntry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = entry_id
    entry.title = "Test Fingerprint Manager"
    entry.data = data or {
        CONF_SENSOR_ENTITY: "sensor.fingerprint_last_id",
        CONF_EVENT_TYPE: DEFAULT_EVENT_TYPE,
        CONF_ESPHOME_DEVICE: "fingerprint_reader",
    }
    entry.options = options or {}
    return entry


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def hass(event_loop):
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)

    # bus
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    hass.bus.async_fire = MagicMock()

    # config_entries
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    # services
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    return hass


@pytest.fixture
def config_entry():
    return make_config_entry()


@pytest.fixture
def config_entry_with_fingerprints():
    return make_config_entry(
        options={
            FINGERPRINT_STORAGE: {
                "1": {"fingerprint_id": 1, "user": "Alice", "label": "Left index"},
                "2": {"fingerprint_id": 2, "user": "Bob", "label": "Right thumb"},
            }
        }
    )
