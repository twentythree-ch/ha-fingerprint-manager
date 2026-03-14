"""Tests for the Fingerprint Manager config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from homeassistant import config_entries

from custom_components.fingerprint_manager.config_flow import (
    FingerprintManagerConfigFlow,
    FingerprintManagerOptionsFlow,
)
from custom_components.fingerprint_manager.const import (
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_TYPE,
    CONF_SENSOR_ENTITY,
    DEFAULT_EVENT_TYPE,
)

from .conftest import make_config_entry


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_hass(sensor_exists: bool = True):
    hass = MagicMock()
    if sensor_exists:
        hass.states.get = MagicMock(return_value=MagicMock())
    else:
        hass.states.get = MagicMock(return_value=None)
    return hass


def _flow(hass) -> FingerprintManagerConfigFlow:
    flow = FingerprintManagerConfigFlow()
    flow.hass = hass
    return flow


# ── Config flow ───────────────────────────────────────────────────────────────

class TestConfigFlow:
    @pytest.mark.asyncio
    async def test_shows_form_without_input(self):
        flow = _flow(_make_hass())
        result = await flow.async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_creates_entry_with_valid_input(self):
        flow = _flow(_make_hass(sensor_exists=True))

        user_input = {
            "name": "My Reader",
            CONF_SENSOR_ENTITY: "sensor.fp_last_id",
            CONF_EVENT_TYPE: DEFAULT_EVENT_TYPE,
            CONF_ESPHOME_DEVICE: "my_device",
        }

        result = await flow.async_step_user(user_input)

        assert result["type"] == "create_entry"
        assert result["title"] == "My Reader"
        assert result["data"][CONF_SENSOR_ENTITY] == "sensor.fp_last_id"

    @pytest.mark.asyncio
    async def test_error_when_sensor_not_found(self):
        flow = _flow(_make_hass(sensor_exists=False))

        user_input = {
            "name": "My Reader",
            CONF_SENSOR_ENTITY: "sensor.nonexistent",
            CONF_EVENT_TYPE: DEFAULT_EVENT_TYPE,
        }

        result = await flow.async_step_user(user_input)

        assert result["type"] == "form"
        assert "entity_not_found" in result["errors"].get(CONF_SENSOR_ENTITY, "")

    @pytest.mark.asyncio
    async def test_creates_entry_without_sensor(self):
        """Sensor entity is optional – entry should be created with event-only config."""
        flow = _flow(_make_hass())

        user_input = {
            "name": "Event Only",
            CONF_EVENT_TYPE: DEFAULT_EVENT_TYPE,
        }

        result = await flow.async_step_user(user_input)

        assert result["type"] == "create_entry"

    def test_async_get_options_flow(self):
        entry = make_config_entry()
        options_flow = FingerprintManagerConfigFlow.async_get_options_flow(entry)
        assert isinstance(options_flow, FingerprintManagerOptionsFlow)


# ── Options flow ──────────────────────────────────────────────────────────────

class TestOptionsFlow:
    def _options_flow(self, hass, entry=None) -> FingerprintManagerOptionsFlow:
        if entry is None:
            entry = make_config_entry()
        flow = FingerprintManagerOptionsFlow(entry)
        flow.hass = hass
        return flow

    @pytest.mark.asyncio
    async def test_shows_form_without_input(self):
        flow = self._options_flow(_make_hass())
        result = await flow.async_step_init(None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_saves_valid_options(self):
        flow = self._options_flow(_make_hass(sensor_exists=True))

        user_input = {
            CONF_SENSOR_ENTITY: "sensor.fp_last_id",
            CONF_EVENT_TYPE: "esphome.my_scan",
            CONF_ESPHOME_DEVICE: "fp_device",
        }

        result = await flow.async_step_init(user_input)

        assert result["type"] == "create_entry"
        assert result["data"][CONF_EVENT_TYPE] == "esphome.my_scan"

    @pytest.mark.asyncio
    async def test_error_when_sensor_not_found(self):
        flow = self._options_flow(_make_hass(sensor_exists=False))

        user_input = {
            CONF_SENSOR_ENTITY: "sensor.ghost",
            CONF_EVENT_TYPE: DEFAULT_EVENT_TYPE,
        }

        result = await flow.async_step_init(user_input)

        assert result["type"] == "form"
        assert "entity_not_found" in result["errors"].get(CONF_SENSOR_ENTITY, "")

    def test_current_helper_prefers_options(self):
        entry = make_config_entry(
            data={CONF_EVENT_TYPE: "data_event"},
            options={CONF_EVENT_TYPE: "options_event"},
        )
        flow = self._options_flow(_make_hass(), entry)
        assert flow._current(CONF_EVENT_TYPE) == "options_event"

    def test_current_helper_falls_back_to_data(self):
        entry = make_config_entry(
            data={CONF_EVENT_TYPE: "data_event"},
            options={},
        )
        flow = self._options_flow(_make_hass(), entry)
        assert flow._current(CONF_EVENT_TYPE) == "data_event"
