"""Config flow for Fingerprint Manager."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_TYPE,
    CONF_SENSOR_ENTITY,
    DEFAULT_EVENT_TYPE,
    DOMAIN,
)


class FingerprintManagerConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN  # type: ignore[call-arg]
):
    """Handle the initial configuration UI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            sensor_entity = user_input.get(CONF_SENSOR_ENTITY)
            if sensor_entity and self.hass.states.get(sensor_entity) is None:
                errors[CONF_SENSOR_ENTITY] = "entity_not_found"

            if not errors:
                return self.async_create_entry(
                    title=user_input.get("name", "Fingerprint Manager"),
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default="Fingerprint Manager"): str,
                    vol.Optional(CONF_SENSOR_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor"),
                    ),
                    vol.Optional(
                        CONF_EVENT_TYPE, default=DEFAULT_EVENT_TYPE
                    ): str,
                    vol.Optional(CONF_ESPHOME_DEVICE): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> "FingerprintManagerOptionsFlow":
        return FingerprintManagerOptionsFlow(config_entry)


class FingerprintManagerOptionsFlow(config_entries.OptionsFlow):
    """Handle option updates (sensor entity, event type, ESPHome device name)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            sensor_entity = user_input.get(CONF_SENSOR_ENTITY)
            if sensor_entity and self.hass.states.get(sensor_entity) is None:
                errors[CONF_SENSOR_ENTITY] = "entity_not_found"

            if not errors:
                return self.async_create_entry(title="", data=user_input)

        current_sensor = self._current(CONF_SENSOR_ENTITY, "")
        current_event = self._current(CONF_EVENT_TYPE, DEFAULT_EVENT_TYPE)
        current_device = self._current(CONF_ESPHOME_DEVICE, "")

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_SENSOR_ENTITY, default=current_sensor): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor"),
                    ),
                    vol.Optional(CONF_EVENT_TYPE, default=current_event): str,
                    vol.Optional(CONF_ESPHOME_DEVICE, default=current_device): str,
                }
            ),
            errors=errors,
        )

    def _current(self, key: str, default: str = "") -> str:
        return self.config_entry.options.get(key) or self.config_entry.data.get(key, default)
