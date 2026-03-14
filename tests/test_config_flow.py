"""Tests for the Fingerprint Manager config flow."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.fingerprint_manager.config_flow import (
    FingerprintManagerConfigFlow,
    FingerprintManagerOptionsFlow,
)
from custom_components.fingerprint_manager.const import (
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_PREFIX,
    CONF_SENSOR_ENTITY,
)

from .conftest import make_config_entry


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_hass(sensor_exists: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.states.get = MagicMock(
        return_value=MagicMock() if sensor_exists else None
    )
    return hass


def _flow(hass) -> FingerprintManagerConfigFlow:
    flow = FingerprintManagerConfigFlow()
    flow.hass = hass
    return flow


# ── Config flow ───────────────────────────────────────────────────────────────

class TestConfigFlow:
    async def test_shows_form_without_input(self):
        result = await _flow(_make_hass()).async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_creates_entry_with_all_fields(self):
        user_input = {
            "name": "Garage Reader",
            CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
            CONF_ESPHOME_DEVICE: "esphome_garage_fingerprint",
            CONF_SENSOR_ENTITY: "sensor.fp_id",
        }
        result = await _flow(_make_hass(sensor_exists=True)).async_step_user(user_input)
        assert result["type"] == "create_entry"
        assert result["title"] == "Garage Reader"
        assert result["data"][CONF_EVENT_PREFIX] == "esphome.garage_fingerprint"

    async def test_creates_entry_without_sensor(self):
        """Sensor field is optional."""
        user_input = {
            "name": "No Sensor",
            CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
            CONF_ESPHOME_DEVICE: "esphome_garage_fingerprint",
        }
        result = await _flow(_make_hass()).async_step_user(user_input)
        assert result["type"] == "create_entry"

    async def test_creates_entry_without_esphome_device(self):
        """ESPHome device is optional (mappings-only mode)."""
        user_input = {
            "name": "Mappings Only",
            CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
        }
        result = await _flow(_make_hass()).async_step_user(user_input)
        assert result["type"] == "create_entry"

    async def test_error_when_sensor_entity_not_found(self):
        user_input = {
            "name": "Bad Sensor",
            CONF_SENSOR_ENTITY: "sensor.nonexistent",
        }
        result = await _flow(_make_hass(sensor_exists=False)).async_step_user(user_input)
        assert result["type"] == "form"
        assert result["errors"].get(CONF_SENSOR_ENTITY) == "entity_not_found"

    def test_async_get_options_flow_returns_options_flow(self):
        options_flow = FingerprintManagerConfigFlow.async_get_options_flow(
            make_config_entry()
        )
        assert isinstance(options_flow, FingerprintManagerOptionsFlow)


# ── Options flow ──────────────────────────────────────────────────────────────

class TestOptionsFlow:
    def _flow(self, hass, entry=None) -> FingerprintManagerOptionsFlow:
        flow = FingerprintManagerOptionsFlow(entry or make_config_entry())
        flow.hass = hass
        return flow

    async def test_shows_form_without_input(self):
        result = await self._flow(_make_hass()).async_step_init(None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    async def test_saves_valid_options(self):
        user_input = {
            CONF_EVENT_PREFIX: "esphome.new_prefix",
            CONF_ESPHOME_DEVICE: "new_device",
        }
        result = await self._flow(_make_hass()).async_step_init(user_input)
        assert result["type"] == "create_entry"
        assert result["data"][CONF_EVENT_PREFIX] == "esphome.new_prefix"

    async def test_error_when_sensor_not_found(self):
        user_input = {
            CONF_SENSOR_ENTITY: "sensor.ghost",
            CONF_EVENT_PREFIX: "esphome.prefix",
        }
        result = await self._flow(_make_hass(sensor_exists=False)).async_step_init(user_input)
        assert result["type"] == "form"
        assert result["errors"].get(CONF_SENSOR_ENTITY) == "entity_not_found"

    def test_current_prefers_options_over_data(self):
        entry = make_config_entry(
            data={CONF_EVENT_PREFIX: "from_data"},
            options={CONF_EVENT_PREFIX: "from_options"},
        )
        flow = self._flow(_make_hass(), entry)
        assert flow._current(CONF_EVENT_PREFIX) == "from_options"

    def test_current_falls_back_to_data(self):
        entry = make_config_entry(
            data={CONF_EVENT_PREFIX: "from_data"},
            options={},
        )
        flow = self._flow(_make_hass(), entry)
        assert flow._current(CONF_EVENT_PREFIX) == "from_data"

    def test_current_returns_default_when_missing(self):
        entry = make_config_entry(data={}, options={})
        flow = self._flow(_make_hass(), entry)
        assert flow._current(CONF_EVENT_PREFIX) == ""
