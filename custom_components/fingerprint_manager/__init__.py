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
    SERVICE_DELETE_ALL_FINGERPRINTS,
    SERVICE_DELETE_FINGERPRINT,
    SERVICE_START_ENROLLMENT,
    SERVICE_UPDATE_FINGERPRINT,
)
from .coordinator import FingerprintManagerCoordinator

PLATFORMS = ["sensor"]

_FINGERPRINT_ID_FIELD = vol.All(vol.Coerce(int), vol.Range(min=1, max=200))


def _coordinator(hass: HomeAssistant, entry_id: str) -> FingerprintManagerCoordinator:
    """Return the coordinator for a specific config entry."""
    return hass.data[DOMAIN][entry_id]


def _any_coordinator(hass: HomeAssistant) -> FingerprintManagerCoordinator:
    """Return the first available coordinator (for services without a target entry)."""
    return next(iter(hass.data[DOMAIN].values()))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Fingerprint Manager from a config entry."""
    coordinator = FingerprintManagerCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services only once (on the first config-entry setup).
    if hass.services.has_service(DOMAIN, SERVICE_START_ENROLLMENT):
        return True

    # ── Service: start_enrollment ─────────────────────────────────────────────
    async def handle_start_enrollment(call: ServiceCall) -> None:
        coord = _any_coordinator(hass)
        await coord.async_start_enrollment(
            fingerprint_id=call.data[ATTR_FINGERPRINT_ID],
            user=call.data[ATTR_USER],
            label=call.data.get(ATTR_LABEL, ""),
            num_scans=call.data.get(ATTR_NUM_SCANS, 2),
        )

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
        await _any_coordinator(hass).async_cancel_enrollment()

    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_ENROLLMENT,
        handle_cancel_enrollment,
    )

    # ── Service: delete_fingerprint ───────────────────────────────────────────
    async def handle_delete_fingerprint(call: ServiceCall) -> None:
        await _any_coordinator(hass).async_delete_fingerprint(
            call.data[ATTR_FINGERPRINT_ID]
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_FINGERPRINT,
        handle_delete_fingerprint,
        schema=vol.Schema({vol.Required(ATTR_FINGERPRINT_ID): _FINGERPRINT_ID_FIELD}),
    )

    # ── Service: delete_all_fingerprints ─────────────────────────────────────
    async def handle_delete_all(call: ServiceCall) -> None:  # noqa: ARG001
        await _any_coordinator(hass).async_delete_all_fingerprints()

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_ALL_FINGERPRINTS,
        handle_delete_all,
    )

    # ── Service: update_fingerprint ───────────────────────────────────────────
    async def handle_update_fingerprint(call: ServiceCall) -> None:
        await _any_coordinator(hass).async_update_fingerprint(
            fingerprint_id=call.data[ATTR_FINGERPRINT_ID],
            user=call.data.get(ATTR_USER),
            label=call.data.get(ATTR_LABEL),
        )

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

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Remove services only when the last entry has been removed.
    if not hass.data.get(DOMAIN):
        for service in (
            SERVICE_START_ENROLLMENT,
            SERVICE_CANCEL_ENROLLMENT,
            SERVICE_DELETE_FINGERPRINT,
            SERVICE_DELETE_ALL_FINGERPRINTS,
            SERVICE_UPDATE_FINGERPRINT,
        ):
            hass.services.async_remove(DOMAIN, service)

    return unload_ok
