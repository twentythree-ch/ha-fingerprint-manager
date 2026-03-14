"""Data coordinator for Fingerprint Manager."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    ATTR_CONFIDENCE,
    ATTR_FINGERPRINT_ID,
    ATTR_LABEL,
    ATTR_MATCHED,
    ATTR_USER,
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_TYPE,
    CONF_SENSOR_ENTITY,
    DEFAULT_EVENT_TYPE,
    DOMAIN,
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_SCAN,
    FINGERPRINT_STORAGE,
    STATE_ENROLLING,
    STATE_IDLE,
    STATE_MATCHED,
    STATE_UNKNOWN_FINGER,
)

_LOGGER = logging.getLogger(__name__)


class FingerprintEntry:
    """Represents a single fingerprint → user mapping."""

    def __init__(self, fingerprint_id: int, user: str, label: str = "") -> None:
        self.fingerprint_id = fingerprint_id
        self.user = user
        self.label = label

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint_id": self.fingerprint_id,
            "user": self.user,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FingerprintEntry":
        return cls(
            fingerprint_id=int(data["fingerprint_id"]),
            user=data["user"],
            label=data.get("label", ""),
        )


class FingerprintManagerCoordinator(DataUpdateCoordinator):
    """Manages the fingerprint database and listens for scan events / sensor changes."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self.config_entry = config_entry

        self._fingerprints: dict[int, FingerprintEntry] = {}
        self._status: str = STATE_IDLE
        self._last_user: str | None = None
        self._last_fingerprint_id: int | None = None
        self._enrolling_fingerprint_id: int | None = None
        self._enrolling_user: str | None = None

        self._unsub_listeners: list[Any] = []

    # ── Public read-only properties ───────────────────────────────────────────

    @property
    def fingerprints(self) -> dict[int, FingerprintEntry]:
        return self._fingerprints

    @property
    def status(self) -> str:
        return self._status

    @property
    def last_user(self) -> str | None:
        return self._last_user

    @property
    def last_fingerprint_id(self) -> int | None:
        return self._last_fingerprint_id

    # ── Setup / teardown ──────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Load persisted fingerprints and attach listeners."""
        self._load_fingerprints()

        sensor_entity = self._option_or_data(CONF_SENSOR_ENTITY)
        if sensor_entity:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass,
                    [sensor_entity],
                    self._handle_sensor_state_change,
                )
            )
            _LOGGER.debug("Monitoring sensor entity: %s", sensor_entity)

        event_type = self._option_or_data(CONF_EVENT_TYPE) or DEFAULT_EVENT_TYPE
        self._unsub_listeners.append(
            self.hass.bus.async_listen(event_type, self._handle_esphome_event)
        )
        _LOGGER.debug("Listening to HA event: %s", event_type)

        # Initialise coordinator data so entities have a value on start-up.
        self.async_set_updated_data(self._build_data_snapshot())

    @callback
    def async_teardown(self) -> None:
        """Remove all listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _option_or_data(self, key: str) -> Any:
        """Return the option value, falling back to config-entry data."""
        return self.config_entry.options.get(key) or self.config_entry.data.get(key)

    def _load_fingerprints(self) -> None:
        """Load fingerprints from config-entry options."""
        raw: dict[str, Any] = self.config_entry.options.get(FINGERPRINT_STORAGE, {})
        self._fingerprints = {
            int(fp_id): FingerprintEntry.from_dict(fp_data)
            for fp_id, fp_data in raw.items()
        }
        _LOGGER.debug("Loaded %d fingerprint(s) from storage", len(self._fingerprints))

    async def _save_fingerprints(self) -> None:
        """Persist fingerprints in config-entry options."""
        options = dict(self.config_entry.options)
        options[FINGERPRINT_STORAGE] = {
            str(fp_id): fp.to_dict() for fp_id, fp in self._fingerprints.items()
        }
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    def _build_data_snapshot(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "last_user": self._last_user,
            "last_fingerprint_id": self._last_fingerprint_id,
            "fingerprints": {
                fp_id: fp.to_dict() for fp_id, fp in self._fingerprints.items()
            },
        }

    def _process_scan(self, fingerprint_id: int, confidence: int | None = None) -> None:
        """Look up a fingerprint ID and fire the enriched scan event."""
        self._last_fingerprint_id = fingerprint_id

        if fingerprint_id in self._fingerprints:
            fp = self._fingerprints[fingerprint_id]
            self._last_user = fp.user
            self._status = STATE_MATCHED
            matched = True
            user = fp.user
            label = fp.label
            _LOGGER.info(
                "Fingerprint matched: id=%d user=%s label=%s", fingerprint_id, user, label
            )
        else:
            self._last_user = None
            self._status = STATE_UNKNOWN_FINGER
            matched = False
            user = None
            label = None
            _LOGGER.info("Unknown fingerprint scanned: id=%d", fingerprint_id)

        event_data: dict[str, Any] = {
            ATTR_FINGERPRINT_ID: fingerprint_id,
            ATTR_USER: user,
            ATTR_LABEL: label,
            ATTR_MATCHED: matched,
            "config_entry_id": self.config_entry.entry_id,
        }
        if confidence is not None:
            event_data[ATTR_CONFIDENCE] = confidence

        self.hass.bus.async_fire(EVENT_FINGERPRINT_SCAN, event_data)
        self.async_set_updated_data(self._build_data_snapshot())

    # ── Sensor state-change handler ───────────────────────────────────────────

    @callback
    def _handle_sensor_state_change(self, event: Event) -> None:
        """Handle a state change from the ESPHome fingerprint sensor."""
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        state_str = new_state.state
        if state_str in ("unavailable", "unknown", "", None):
            return

        try:
            fingerprint_id = int(float(state_str))
        except (ValueError, TypeError):
            _LOGGER.debug("Cannot parse fingerprint ID from state '%s'", state_str)
            return

        if fingerprint_id <= 0:
            if self._status != STATE_ENROLLING:
                self._status = STATE_IDLE
                self._last_fingerprint_id = None
                self._last_user = None
                self.async_set_updated_data(self._build_data_snapshot())
            return

        # Avoid re-processing when the sensor value hasn't changed.
        old_str = old_state.state if old_state else None
        if old_str == state_str:
            return

        self._process_scan(fingerprint_id)

    # ── ESPHome event handler ─────────────────────────────────────────────────

    @callback
    def _handle_esphome_event(self, event: Event) -> None:
        """Handle an esphome.fingerprint_scan (or custom) HA event."""
        data = event.data

        # Support both integer and string values emitted by ESPHome templates.
        try:
            fingerprint_id = int(float(str(data.get("finger_id", 0))))
        except (ValueError, TypeError):
            _LOGGER.debug("Cannot parse finger_id from event data: %s", data)
            return

        if fingerprint_id <= 0:
            return

        try:
            confidence: int | None = int(float(str(data.get("confidence", 0)))) or None
        except (ValueError, TypeError):
            confidence = None

        self._process_scan(fingerprint_id, confidence)

    # ── Service handlers (called from __init__.py) ────────────────────────────

    async def async_start_enrollment(
        self, fingerprint_id: int, user: str, label: str = "", num_scans: int = 2
    ) -> None:
        """Pre-register a mapping and call the ESPHome enroll service."""
        self._enrolling_fingerprint_id = fingerprint_id
        self._enrolling_user = user
        self._status = STATE_ENROLLING

        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            service_name = f"{esphome_device}_fingerprint_enroll"
            try:
                await self.hass.services.async_call(
                    "esphome",
                    service_name,
                    {"num_scans": num_scans, "fingerprint_id": fingerprint_id},
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome enroll service: %s", err)

        # Optimistically register the mapping so scans are recognised immediately.
        self._fingerprints[fingerprint_id] = FingerprintEntry(
            fingerprint_id=fingerprint_id, user=user, label=label
        )
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_data_snapshot())

        self.hass.bus.async_fire(
            EVENT_FINGERPRINT_ENROLLED,
            {
                ATTR_FINGERPRINT_ID: fingerprint_id,
                ATTR_USER: user,
                ATTR_LABEL: label,
                "config_entry_id": self.config_entry.entry_id,
            },
        )
        _LOGGER.info(
            "Started enrollment: id=%d user=%s label=%s", fingerprint_id, user, label
        )

    async def async_cancel_enrollment(self) -> None:
        """Cancel the current enrollment."""
        self._enrolling_fingerprint_id = None
        self._enrolling_user = None
        self._status = STATE_IDLE

        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            service_name = f"{esphome_device}_fingerprint_cancel_enroll"
            try:
                await self.hass.services.async_call(
                    "esphome", service_name, {}, blocking=True
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome cancel-enroll service: %s", err)

        self.async_set_updated_data(self._build_data_snapshot())

    async def async_delete_fingerprint(self, fingerprint_id: int) -> None:
        """Delete a fingerprint mapping."""
        if fingerprint_id not in self._fingerprints:
            _LOGGER.warning("delete_fingerprint: ID %d not found", fingerprint_id)
            return
        del self._fingerprints[fingerprint_id]
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_data_snapshot())
        _LOGGER.info("Deleted fingerprint id=%d", fingerprint_id)

    async def async_update_fingerprint(
        self,
        fingerprint_id: int,
        user: str | None = None,
        label: str | None = None,
    ) -> None:
        """Update the user and/or label of an existing fingerprint mapping."""
        if fingerprint_id not in self._fingerprints:
            _LOGGER.warning("update_fingerprint: ID %d not found", fingerprint_id)
            return
        fp = self._fingerprints[fingerprint_id]
        if user is not None:
            fp.user = user
        if label is not None:
            fp.label = label
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_data_snapshot())
        _LOGGER.info("Updated fingerprint id=%d", fingerprint_id)
