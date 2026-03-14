"""Device triggers for Fingerprint Manager."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.device_automation import DEVICE_TRIGGER_BASE_SCHEMA
from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_PLATFORM, CONF_TYPE
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.trigger import TriggerActionType, TriggerInfo

from .const import (
    ATTR_MATCHED,
    DOMAIN,
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_ENROLLMENT_FAILED,
    EVENT_FINGERPRINT_SCAN,
)

TRIGGER_TYPE_FINGERPRINT_SCANNED = "fingerprint_scanned"
TRIGGER_TYPE_FINGERPRINT_MATCHED = "fingerprint_matched"
TRIGGER_TYPE_FINGERPRINT_ENROLLED = "fingerprint_enrolled"
TRIGGER_TYPE_ENROLLMENT_FAILED = "enrollment_failed"

TRIGGER_TYPES = frozenset(
    {
        TRIGGER_TYPE_FINGERPRINT_SCANNED,
        TRIGGER_TYPE_FINGERPRINT_MATCHED,
        TRIGGER_TYPE_FINGERPRINT_ENROLLED,
        TRIGGER_TYPE_ENROLLMENT_FAILED,
    }
)

TRIGGER_SCHEMA = DEVICE_TRIGGER_BASE_SCHEMA.extend(
    {
        vol.Required(CONF_TYPE): vol.In(TRIGGER_TYPES),
    }
)

# Map each trigger type to the HA bus event it listens for.
_EVENT_MAP: dict[str, str] = {
    TRIGGER_TYPE_FINGERPRINT_SCANNED: EVENT_FINGERPRINT_SCAN,
    TRIGGER_TYPE_FINGERPRINT_MATCHED: EVENT_FINGERPRINT_SCAN,
    TRIGGER_TYPE_FINGERPRINT_ENROLLED: EVENT_FINGERPRINT_ENROLLED,
    TRIGGER_TYPE_ENROLLMENT_FAILED: EVENT_FINGERPRINT_ENROLLMENT_FAILED,
}


async def async_get_triggers(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """Return a list of triggers for the given device."""
    return [
        {
            CONF_PLATFORM: "device",
            CONF_DOMAIN: DOMAIN,
            CONF_DEVICE_ID: device_id,
            CONF_TYPE: trigger_type,
        }
        for trigger_type in TRIGGER_TYPES
    ]


async def async_attach_trigger(
    hass: HomeAssistant,
    config: dict[str, Any],
    action: TriggerActionType,
    trigger_info: TriggerInfo,
) -> CALLBACK_TYPE:
    """Attach a trigger and return an unsubscribe callback."""
    trigger_type: str = config[CONF_TYPE]
    device_id: str = config[CONF_DEVICE_ID]
    event_type: str = _EVENT_MAP[trigger_type]

    # Resolve config_entry_id so that events from other Fingerprint Manager
    # devices do not accidentally fire this trigger.
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    config_entry_id: str | None = None
    if device:
        for identifier in device.identifiers:
            if identifier[0] == DOMAIN:
                config_entry_id = identifier[1]
                break

    trigger_data: dict[str, Any] = {
        **trigger_info.get("trigger_data", {}),
        CONF_PLATFORM: "device",
        CONF_DOMAIN: DOMAIN,
        CONF_DEVICE_ID: device_id,
        CONF_TYPE: trigger_type,
    }

    @callback
    def _event_handler(event: Event) -> None:
        # Filter to events that belong to this specific device.
        if config_entry_id and event.data.get("config_entry_id") != config_entry_id:
            return
        # "fingerprint_matched" only fires when the scan was a positive match.
        if trigger_type == TRIGGER_TYPE_FINGERPRINT_MATCHED and not event.data.get(
            ATTR_MATCHED
        ):
            return
        hass.async_create_task(
            action(
                {
                    "trigger": {
                        **trigger_data,
                        "event": event,
                        "description": f"Fingerprint Manager {trigger_type}",
                    }
                }
            )
        )

    return hass.bus.async_listen(event_type, _event_handler)
