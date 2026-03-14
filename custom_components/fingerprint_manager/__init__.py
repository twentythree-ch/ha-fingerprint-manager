"""Fingerprint Manager integration setup."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_FINGERPRINT_ID,
    ATTR_LABEL,
    ATTR_NUM_SCANS,
    ATTR_USER,
    DOMAIN,
    SERVICE_CANCEL_ENROLLMENT,
    SERVICE_DELETE_FINGERPRINT,
    SERVICE_START_ENROLLMENT,
    SERVICE_UPDATE_FINGERPRINT,
)
from .coordinator import FingerprintManagerCoordinator

PLATFORMS = ["sensor"]

_FINGERPRINT_ID_FIELD = vol.All(vol.Coerce(int), vol.Range(min=1, max=200))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fingerprint Manager from a config entry."""
    coordinator = FingerprintManagerCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # ── Service: start_enrollment ─────────────────────────────────────────────
    async def handle_start_enrollment(call: ServiceCall) -> None:
        fingerprint_id: int = call.data[ATTR_FINGERPRINT_ID]
        user: str = call.data[ATTR_USER]
        label: str = call.data.get(ATTR_LABEL, "")
        num_scans: int = call.data.get(ATTR_NUM_SCANS, 2)
        await coordinator.async_start_enrollment(fingerprint_id, user, label, num_scans)

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_ENROLLMENT,
        handle_start_enrollment,
        schema=vol.Schema(
            {
                vol.Required(ATTR_FINGERPRINT_ID): _FINGERPRINT_ID_FIELD,
                vol.Required(ATTR_USER): cv.string,
                vol.Optional(ATTR_LABEL, default=""): cv.string,
                vol.Optional(ATTR_NUM_SCANS, default=2): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=10)
                ),
            }
        ),
    )

    # ── Service: cancel_enrollment ────────────────────────────────────────────
    async def handle_cancel_enrollment(call: ServiceCall) -> None:  # noqa: ARG001
        await coordinator.async_cancel_enrollment()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_ENROLLMENT,
        handle_cancel_enrollment,
    )

    # ── Service: delete_fingerprint ───────────────────────────────────────────
    async def handle_delete_fingerprint(call: ServiceCall) -> None:
        fingerprint_id: int = call.data[ATTR_FINGERPRINT_ID]
        await coordinator.async_delete_fingerprint(fingerprint_id)

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FINGERPRINT,
        handle_delete_fingerprint,
        schema=vol.Schema(
            {
                vol.Required(ATTR_FINGERPRINT_ID): _FINGERPRINT_ID_FIELD,
            }
        ),
    )

    # ── Service: update_fingerprint ───────────────────────────────────────────
    async def handle_update_fingerprint(call: ServiceCall) -> None:
        fingerprint_id: int = call.data[ATTR_FINGERPRINT_ID]
        user: str | None = call.data.get(ATTR_USER)
        label: str | None = call.data.get(ATTR_LABEL)
        await coordinator.async_update_fingerprint(fingerprint_id, user, label)

    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_FINGERPRINT,
        handle_update_fingerprint,
        schema=vol.Schema(
            {
                vol.Required(ATTR_FINGERPRINT_ID): _FINGERPRINT_ID_FIELD,
                vol.Optional(ATTR_USER): cv.string,
                vol.Optional(ATTR_LABEL): cv.string,
            }
        ),
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: FingerprintManagerCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_teardown()

    # Unregister services only when the last entry is removed.
    if len(hass.data[DOMAIN]) == 1:
        for service in (
            SERVICE_START_ENROLLMENT,
            SERVICE_CANCEL_ENROLLMENT,
            SERVICE_DELETE_FINGERPRINT,
            SERVICE_UPDATE_FINGERPRINT,
        ):
            hass.services.async_remove(DOMAIN, service)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
