"""Config flow for Fingerprint Manager."""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr, selector

from .const import (
    CONF_ESPHOME_DEVICE,
    CONF_ESPHOME_DEVICE_ID,
    CONF_EVENT_PREFIX,
    CONF_SENSOR_ENTITY,
    DOMAIN,
    FINGERPRINT_STORAGE,
)


def _slugify(name: str) -> str:
    """Convert an ESPHome node name to a HA service-compatible slug."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class FingerprintManagerConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN  # type: ignore[call-arg]
):
    """Handle the initial configuration UI (two-step)."""

    VERSION = 1

    def __init__(self) -> None:
        self._name: str = "Fingerprint Manager"
        self._device_id: str | None = None
        self._sensor_entity: str | None = None
        self._derived_device: str = ""
        self._derived_prefix: str = ""

    # ── Step 1: device + sensor ───────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Pick ESPHome device and optional fingerprint-ID sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            sensor_entity = user_input.get(CONF_SENSOR_ENTITY)
            if sensor_entity and self.hass.states.get(sensor_entity) is None:
                errors[CONF_SENSOR_ENTITY] = "entity_not_found"

            if not errors:
                self._name = user_input.get("name", "Fingerprint Manager")
                self._device_id = user_input.get(CONF_ESPHOME_DEVICE_ID) or None
                self._sensor_entity = sensor_entity

                if self._device_id:
                    self._derived_device, self._derived_prefix = (
                        await self._derive_esphome_names(self._device_id)
                    )

                return await self.async_step_configure()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Fingerprint Manager"): str,
                    vol.Optional(CONF_ESPHOME_DEVICE_ID): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(integration="esphome")
                    ),
                    vol.Optional(CONF_SENSOR_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor"),
                    ),
                }
            ),
            errors=errors,
        )

    # ── Step 2: confirm / adjust derived names ────────────────────────────────

    async def async_step_configure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm or adjust the auto-derived event prefix and service name."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._name,
                data={
                    "name": self._name,
                    CONF_ESPHOME_DEVICE_ID: self._device_id,
                    CONF_ESPHOME_DEVICE: user_input.get(CONF_ESPHOME_DEVICE, ""),
                    CONF_EVENT_PREFIX: user_input.get(CONF_EVENT_PREFIX, ""),
                    CONF_SENSOR_ENTITY: self._sensor_entity,
                },
            )

        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_EVENT_PREFIX, default=self._derived_prefix
                    ): str,
                    vol.Optional(
                        CONF_ESPHOME_DEVICE, default=self._derived_device
                    ): str,
                }
            ),
        )

    # ── Shared helper ─────────────────────────────────────────────────────────

    async def _derive_esphome_names(self, device_id: str) -> tuple[str, str]:
        """Return (esphome_device_slug, event_prefix) for an ESPHome device.

        Looks up the ESPHome config entry that owns *device_id* and derives:
          - slug        : node name with non-alphanumeric chars → underscores
          - event_prefix: ``esphome.<slug_without_esphome_prefix>`` (matches
                          the homeassistant.event convention used in the
                          example ESPHome YAML)

        ESPHome node names often start with ``esphome-`` (e.g.
        ``esphome-garage-fingerprint``).  The HA service slug must keep the
        full name (``esphome_garage_fingerprint``), but the event prefix
        convention drops the leading ``esphome_`` so events look like
        ``esphome.garage_fingerprint_finger_scan_matched``.
        """
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get(device_id)
        if device is None:
            return "", ""

        for entry_id in device.config_entries:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == "esphome":
                node_name: str = entry.data.get("name", "")
                if node_name:
                    slug = _slugify(node_name)
                    event_slug = slug.removeprefix("esphome_")
                    return slug, f"esphome.{event_slug}"

        return "", ""

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "FingerprintManagerOptionsFlow":
        return FingerprintManagerOptionsFlow(config_entry)


class FingerprintManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle option updates after initial setup (two-step)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry
        self._device_id: str | None = None
        self._sensor_entity: str | None = None
        self._derived_device: str = ""
        self._derived_prefix: str = ""

    # ── Step 1: device + sensor ───────────────────────────────────────────────

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Pick ESPHome device and optional fingerprint-ID sensor."""
        errors: dict[str, str] = {}

        if user_input is not None:
            sensor_entity = user_input.get(CONF_SENSOR_ENTITY)
            if sensor_entity and self.hass.states.get(sensor_entity) is None:
                errors[CONF_SENSOR_ENTITY] = "entity_not_found"

            if not errors:
                self._device_id = user_input.get(CONF_ESPHOME_DEVICE_ID) or None
                self._sensor_entity = sensor_entity

                if self._device_id:
                    self._derived_device, self._derived_prefix = (
                        await self._derive_esphome_names(self._device_id)
                    )
                else:
                    # No device selected – keep existing text values as defaults.
                    self._derived_device = self._current(CONF_ESPHOME_DEVICE)
                    self._derived_prefix = self._current(CONF_EVENT_PREFIX)

                return await self.async_step_configure()

        current_device_id = self._current(CONF_ESPHOME_DEVICE_ID)
        current_sensor = self._current(CONF_SENSOR_ENTITY)

        schema: dict = {
            vol.Optional(CONF_ESPHOME_DEVICE_ID): selector.DeviceSelector(
                selector.DeviceSelectorConfig(integration="esphome")
            ),
            vol.Optional(CONF_SENSOR_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor"),
            ),
        }
        # Pre-populate defaults for existing values only when they are non-empty
        # so the selectors don't receive an invalid empty-string placeholder.
        if current_device_id:
            schema = {
                vol.Optional(
                    CONF_ESPHOME_DEVICE_ID, default=current_device_id
                ): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="esphome")
                ),
                vol.Optional(
                    CONF_SENSOR_ENTITY,
                    **({"default": current_sensor} if current_sensor else {}),
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
            }
        elif current_sensor:
            schema = {
                vol.Optional(CONF_ESPHOME_DEVICE_ID): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(integration="esphome")
                ),
                vol.Optional(
                    CONF_SENSOR_ENTITY, default=current_sensor
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor"),
                ),
            }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    # ── Step 2: confirm / adjust derived names ────────────────────────────────

    async def async_step_configure(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        """Confirm or adjust the auto-derived event prefix and service name."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    # Preserve fingerprint mappings stored by the coordinator.
                    FINGERPRINT_STORAGE: self.config_entry.options.get(
                        FINGERPRINT_STORAGE, {}
                    ),
                    CONF_ESPHOME_DEVICE_ID: self._device_id,
                    CONF_ESPHOME_DEVICE: user_input.get(CONF_ESPHOME_DEVICE, ""),
                    CONF_EVENT_PREFIX: user_input.get(CONF_EVENT_PREFIX, ""),
                    CONF_SENSOR_ENTITY: self._sensor_entity,
                },
            )

        return self.async_show_form(
            step_id="configure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_EVENT_PREFIX, default=self._derived_prefix
                    ): str,
                    vol.Optional(
                        CONF_ESPHOME_DEVICE, default=self._derived_device
                    ): str,
                }
            ),
        )

    # ── Shared helpers ────────────────────────────────────────────────────────

    async def _derive_esphome_names(self, device_id: str) -> tuple[str, str]:
        """Return (esphome_device_slug, event_prefix) for an ESPHome device."""
        dev_reg = dr.async_get(self.hass)
        device = dev_reg.async_get(device_id)
        if device is None:
            return "", ""

        for entry_id in device.config_entries:
            entry = self.hass.config_entries.async_get_entry(entry_id)
            if entry and entry.domain == "esphome":
                node_name: str = entry.data.get("name", "")
                if node_name:
                    slug = _slugify(node_name)
                    event_slug = slug.removeprefix("esphome_")
                    return slug, f"esphome.{event_slug}"

        return "", ""

    def _current(self, key: str, default: str = "") -> str:
        """Return current option value, falling back to config-entry data."""
        return self.config_entry.options.get(key) or self.config_entry.data.get(
            key, default
        )
