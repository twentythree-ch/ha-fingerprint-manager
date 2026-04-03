"""Tests for the Fingerprint Manager config flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.fingerprint_manager.config_flow import (
    FingerprintManagerConfigFlow,
    FingerprintManagerOptionsFlow,
    _slugify,
)
from custom_components.fingerprint_manager.const import (
    CONF_ESPHOME_DEVICE,
    CONF_ESPHOME_DEVICE_ID,
    CONF_EVENT_PREFIX,
    CONF_SENSOR_ENTITY,
    FINGERPRINT_STORAGE,
)

from .conftest import make_config_entry


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_hass(sensor_exists: bool = True) -> MagicMock:
    hass = MagicMock()
    hass.states.get = MagicMock(
        return_value=MagicMock() if sensor_exists else None
    )
    hass.config_entries = MagicMock()
    hass.config_entries.async_get_entry = MagicMock(return_value=None)
    return hass


def _flow(hass) -> FingerprintManagerConfigFlow:
    flow = FingerprintManagerConfigFlow()
    flow.hass = hass
    return flow


def _make_esphome_entry(node_name: str, *, use_legacy_key: bool = False) -> MagicMock:
    """Return a mock ESPHome config entry with the given node name.

    By default uses ``device_name`` (current ESPHome key).
    Set *use_legacy_key* to store the name under ``name`` instead.
    """
    entry = MagicMock()
    entry.domain = "esphome"
    key = "name" if use_legacy_key else "device_name"
    entry.data = {key: node_name}
    entry.title = node_name
    return entry


# ── _slugify helper ───────────────────────────────────────────────────────────

class TestSlugify:
    def test_hyphens_to_underscores(self):
        assert _slugify("esphome-garage-fingerprint") == "esphome_garage_fingerprint"

    def test_spaces_to_underscores(self):
        assert _slugify("garage fingerprint") == "garage_fingerprint"

    def test_lowercase(self):
        assert _slugify("Garage-Fingerprint") == "garage_fingerprint"

    def test_strips_leading_trailing_underscores(self):
        assert _slugify("-hello-") == "hello"


# ── Config flow: step 1 (user) ────────────────────────────────────────────────

class TestConfigFlow:
    async def test_shows_form_without_input(self):
        result = await _flow(_make_hass()).async_step_user(None)
        assert result["type"] == "form"
        assert result["step_id"] == "user"

    async def test_proceeds_to_configure_step(self):
        user_input = {
            "name": "Garage Reader",
            CONF_ESPHOME_DEVICE_ID: None,
        }
        result = await _flow(_make_hass()).async_step_user(user_input)
        assert result["type"] == "form"
        assert result["step_id"] == "configure"

    async def test_error_when_sensor_entity_not_found(self):
        user_input = {
            "name": "Bad Sensor",
            CONF_SENSOR_ENTITY: "sensor.nonexistent",
        }
        result = await _flow(_make_hass(sensor_exists=False)).async_step_user(user_input)
        assert result["type"] == "form"
        assert result["errors"].get(CONF_SENSOR_ENTITY) == "entity_not_found"

    async def test_derives_names_from_selected_device(self):
        """Selecting a device auto-derives the slug and event prefix, and
        advances to the configure confirmation form."""
        hass = _make_hass()
        device = MagicMock()
        device.config_entries = ["esphome_entry_1"]
        esphome_entry = _make_esphome_entry("esphome-garage-fingerprint")
        hass.config_entries.async_get_entry = MagicMock(return_value=esphome_entry)

        with patch(
            "custom_components.fingerprint_manager.config_flow.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get = MagicMock(return_value=device)
            flow = _flow(hass)
            result = await flow.async_step_user(
                {"name": "Garage", CONF_ESPHOME_DEVICE_ID: "device_abc"}
            )

        # Should show the configure form with derived defaults
        assert result["type"] == "form"
        assert result["step_id"] == "configure"
        assert flow._derived_device == "esphome_garage_fingerprint"
        assert flow._derived_prefix == "esphome.garage_fingerprint"

    async def test_derives_names_from_legacy_name_key(self):
        """ESPHome entries that still use the legacy ``name`` key in data."""
        hass = _make_hass()
        device = MagicMock()
        device.config_entries = ["esphome_entry_1"]
        esphome_entry = _make_esphome_entry("esphome-garage-fingerprint", use_legacy_key=True)
        hass.config_entries.async_get_entry = MagicMock(return_value=esphome_entry)

        with patch(
            "custom_components.fingerprint_manager.config_flow.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get = MagicMock(return_value=device)
            flow = _flow(hass)
            await flow.async_step_user(
                {"name": "Garage", CONF_ESPHOME_DEVICE_ID: "device_abc"}
            )

        assert flow._derived_device == "esphome_garage_fingerprint"
        assert flow._derived_prefix == "esphome.garage_fingerprint"

    async def test_derives_names_from_entry_title_fallback(self):
        """When neither ``device_name`` nor ``name`` exists, fall back to entry.title."""
        hass = _make_hass()
        device = MagicMock()
        device.config_entries = ["esphome_entry_1"]
        entry = MagicMock()
        entry.domain = "esphome"
        entry.data = {}  # no device_name or name key
        entry.title = "esphome-garage-fingerprint"
        hass.config_entries.async_get_entry = MagicMock(return_value=entry)

        with patch(
            "custom_components.fingerprint_manager.config_flow.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get = MagicMock(return_value=device)
            flow = _flow(hass)
            await flow.async_step_user(
                {"name": "Garage", CONF_ESPHOME_DEVICE_ID: "device_abc"}
            )

        assert flow._derived_device == "esphome_garage_fingerprint"
        assert flow._derived_prefix == "esphome.garage_fingerprint"

    async def test_derives_names_and_creates_entry_on_confirm(self):
        """After confirming derived names, the entry is created."""
        hass = _make_hass()
        device = MagicMock()
        device.config_entries = ["esphome_entry_1"]
        esphome_entry = _make_esphome_entry("esphome-garage-fingerprint")
        hass.config_entries.async_get_entry = MagicMock(return_value=esphome_entry)

        with patch(
            "custom_components.fingerprint_manager.config_flow.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get = MagicMock(return_value=device)
            flow = _flow(hass)
            await flow.async_step_user(
                {"name": "Garage", CONF_ESPHOME_DEVICE_ID: "device_abc"}
            )

        result = await flow.async_step_configure(
            {
                CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
                CONF_ESPHOME_DEVICE: "esphome_garage_fingerprint",
            }
        )

        assert result["type"] == "create_entry"
        assert result["title"] == "Garage"
        assert result["data"][CONF_ESPHOME_DEVICE] == "esphome_garage_fingerprint"
        assert result["data"][CONF_EVENT_PREFIX] == "esphome.garage_fingerprint"
        assert result["data"][CONF_ESPHOME_DEVICE_ID] == "device_abc"

    def test_async_get_options_flow_returns_options_flow(self):
        options_flow = FingerprintManagerConfigFlow.async_get_options_flow(
            make_config_entry()
        )
        assert isinstance(options_flow, FingerprintManagerOptionsFlow)


# ── Config flow: step 2 (configure) ──────────────────────────────────────────

class TestConfigFlowConfigure:
    async def _reach_configure(self, hass=None, name="Test") -> FingerprintManagerConfigFlow:
        """Complete step 1 and return the flow object at step 2."""
        flow = _flow(hass or _make_hass())
        flow._name = name
        flow._device_id = None
        flow._sensor_entity = None
        flow._derived_device = ""
        flow._derived_prefix = ""
        return flow

    async def test_creates_entry_on_submit(self):
        flow = await self._reach_configure(name="Garage Reader")
        result = await flow.async_step_configure(
            {
                CONF_EVENT_PREFIX: "esphome.garage_fingerprint",
                CONF_ESPHOME_DEVICE: "esphome_garage_fingerprint",
            }
        )
        assert result["type"] == "create_entry"
        assert result["title"] == "Garage Reader"
        assert result["data"][CONF_EVENT_PREFIX] == "esphome.garage_fingerprint"
        assert result["data"][CONF_ESPHOME_DEVICE] == "esphome_garage_fingerprint"

    async def test_shows_form_without_input(self):
        flow = await self._reach_configure()
        result = await flow.async_step_configure(None)
        assert result["type"] == "form"
        assert result["step_id"] == "configure"

    async def test_stores_device_id_in_data(self):
        flow = await self._reach_configure()
        flow._device_id = "device_xyz"
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "esphome.test", CONF_ESPHOME_DEVICE: "test_device"}
        )
        assert result["data"][CONF_ESPHOME_DEVICE_ID] == "device_xyz"

    async def test_shows_error_when_event_prefix_empty(self):
        """Empty event_prefix must show validation error."""
        flow = await self._reach_configure()
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "", CONF_ESPHOME_DEVICE: "test_device"}
        )
        assert result["type"] == "form"
        assert result["errors"].get(CONF_EVENT_PREFIX) == "required"

    async def test_shows_error_when_esphome_device_empty(self):
        """Empty esphome_device must show validation error."""
        flow = await self._reach_configure()
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "esphome.test", CONF_ESPHOME_DEVICE: ""}
        )
        assert result["type"] == "form"
        assert result["errors"].get(CONF_ESPHOME_DEVICE) == "required"


# ── Options flow: step 1 (init) ───────────────────────────────────────────────

class TestOptionsFlow:
    def _flow(self, hass, entry=None) -> FingerprintManagerOptionsFlow:
        flow = FingerprintManagerOptionsFlow(entry or make_config_entry())
        flow.hass = hass
        return flow

    async def test_shows_form_without_input(self):
        result = await self._flow(_make_hass()).async_step_init(None)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

    async def test_proceeds_to_configure_step(self):
        result = await self._flow(_make_hass()).async_step_init({})
        assert result["type"] == "form"
        assert result["step_id"] == "configure"

    async def test_error_when_sensor_not_found(self):
        user_input = {CONF_SENSOR_ENTITY: "sensor.ghost"}
        result = await self._flow(_make_hass(sensor_exists=False)).async_step_init(user_input)
        assert result["type"] == "form"
        assert result["errors"].get(CONF_SENSOR_ENTITY) == "entity_not_found"

    async def test_derives_names_when_device_selected(self):
        """Selecting a device advances to the configure confirmation form."""
        hass = _make_hass()
        device = MagicMock()
        device.config_entries = ["esphome_entry_1"]
        esphome_entry = _make_esphome_entry("garage-fp")
        hass.config_entries.async_get_entry = MagicMock(return_value=esphome_entry)

        with patch(
            "custom_components.fingerprint_manager.config_flow.dr.async_get"
        ) as mock_dr:
            mock_dr.return_value.async_get = MagicMock(return_value=device)
            flow = self._flow(hass)
            result = await flow.async_step_init(
                {CONF_ESPHOME_DEVICE_ID: "device_abc"}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "configure"
        assert flow._derived_device == "garage_fp"
        assert flow._derived_prefix == "esphome.garage_fp"
        assert flow._device_id == "device_abc"

    async def test_falls_back_to_existing_values_when_no_device(self):
        """When no device is selected, existing text values are kept as defaults."""
        entry = make_config_entry(
            data={
                CONF_EVENT_PREFIX: "esphome.old_prefix",
                CONF_ESPHOME_DEVICE: "old_device",
            }
        )
        flow = self._flow(_make_hass(), entry)
        await flow.async_step_init({})  # no device_id submitted
        assert flow._derived_prefix == "esphome.old_prefix"
        assert flow._derived_device == "old_device"


# ── Options flow: step 2 (configure) ─────────────────────────────────────────

class TestOptionsFlowConfigure:
    def _flow_at_configure(self, hass=None, entry=None) -> FingerprintManagerOptionsFlow:
        flow = FingerprintManagerOptionsFlow(
            entry or make_config_entry(
                options={FINGERPRINT_STORAGE: {"1": {"fingerprint_id": 1, "user": "Alice", "label": ""}}}
            )
        )
        flow.hass = hass or _make_hass()
        flow._device_id = None
        flow._sensor_entity = None
        flow._derived_device = ""
        flow._derived_prefix = ""
        return flow

    async def test_saves_valid_options(self):
        flow = self._flow_at_configure()
        result = await flow.async_step_configure(
            {
                CONF_EVENT_PREFIX: "esphome.new_prefix",
                CONF_ESPHOME_DEVICE: "new_device",
            }
        )
        assert result["type"] == "create_entry"
        assert result["data"][CONF_EVENT_PREFIX] == "esphome.new_prefix"

    async def test_shows_error_when_event_prefix_empty(self):
        """Empty event_prefix must show validation error."""
        flow = self._flow_at_configure()
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "", CONF_ESPHOME_DEVICE: "new_device"}
        )
        assert result["type"] == "form"
        assert result["errors"].get(CONF_EVENT_PREFIX) == "required"

    async def test_shows_error_when_esphome_device_empty(self):
        """Empty esphome_device must show validation error."""
        flow = self._flow_at_configure()
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "esphome.new_prefix", CONF_ESPHOME_DEVICE: ""}
        )
        assert result["type"] == "form"
        assert result["errors"].get(CONF_ESPHOME_DEVICE) == "required"

    async def test_preserves_fingerprint_storage(self):
        """Saving options must NOT wipe existing fingerprint mappings."""
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {"5": {"fingerprint_id": 5, "user": "Bob", "label": ""}},
            }
        )
        flow = self._flow_at_configure(entry=entry)
        result = await flow.async_step_configure(
            {CONF_EVENT_PREFIX: "esphome.test", CONF_ESPHOME_DEVICE: "test_device"}
        )
        assert FINGERPRINT_STORAGE in result["data"]
        assert "5" in result["data"][FINGERPRINT_STORAGE]

    async def test_shows_form_without_input(self):
        result = await self._flow_at_configure().async_step_configure(None)
        assert result["type"] == "form"
        assert result["step_id"] == "configure"

    def test_current_prefers_options_over_data(self):
        entry = make_config_entry(
            data={CONF_EVENT_PREFIX: "from_data"},
            options={CONF_EVENT_PREFIX: "from_options"},
        )
        flow = FingerprintManagerOptionsFlow(entry)
        assert flow._current(CONF_EVENT_PREFIX) == "from_options"

    def test_current_falls_back_to_data(self):
        entry = make_config_entry(
            data={CONF_EVENT_PREFIX: "from_data"},
            options={},
        )
        flow = FingerprintManagerOptionsFlow(entry)
        assert flow._current(CONF_EVENT_PREFIX) == "from_data"

    def test_current_returns_default_when_missing(self):
        entry = make_config_entry(data={}, options={})
        flow = FingerprintManagerOptionsFlow(entry)
        assert flow._current(CONF_EVENT_PREFIX) == ""
