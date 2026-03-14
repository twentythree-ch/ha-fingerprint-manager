"""pytest configuration and shared fixtures for Fingerprint Manager tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.config_entries import ConfigEntry

from custom_components.fingerprint_manager.const import (
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_PREFIX,
    CONF_SENSOR_ENTITY,
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
    entry.data = data if data is not None else {
        CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
        CONF_ESPHOME_DEVICE: "esphome_garage_fingerprint",
        CONF_SENSOR_ENTITY: "sensor.garage_fingerprint_fingerprint_id",
    }
    entry.options = options if options is not None else {}
    return entry


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def hass():
    """Return a minimal mock HomeAssistant instance."""
    hass = MagicMock()

    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)

    # bus – async_listen returns a plain callable (the unsub function)
    hass.bus = MagicMock()
    hass.bus.async_listen = MagicMock(return_value=lambda: None)
    hass.bus.async_fire = MagicMock()

    # config_entries
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    # services
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()

    # async_create_task (used by _handle_enrollment_failed).
    # Close the coroutine so Python doesn't warn about it being unawaited.
    def _close_coro(coro):
        if hasattr(coro, "close"):
            coro.close()

    hass.async_create_task = MagicMock(side_effect=_close_coro)

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
