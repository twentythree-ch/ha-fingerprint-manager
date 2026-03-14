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
    ATTR_NUM_SCANS,
    ATTR_SCAN_NUM,
    ATTR_USER,
    CONF_ESPHOME_DEVICE,
    CONF_EVENT_PREFIX,
    CONF_SENSOR_ENTITY,
    DOMAIN,
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_ENROLLMENT_FAILED,
    EVENT_FINGERPRINT_SCAN,
    EVENT_SUFFIX_ENROLLMENT_DONE,
    EVENT_SUFFIX_ENROLLMENT_FAILED,
    EVENT_SUFFIX_ENROLLMENT_SCAN,
    EVENT_SUFFIX_INVALID,
    EVENT_SUFFIX_MATCHED,
    EVENT_SUFFIX_MISPLACED,
    EVENT_SUFFIX_UNMATCHED,
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


def _parse_int(value: Any, default: int = 0) -> int:
    """Safely parse a value (int, float, or numeric string) to int."""
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return default


class FingerprintManagerCoordinator(DataUpdateCoordinator):
    """Manages the fingerprint database and listens for ESPHome events."""

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
        # Fingerprint ID being enrolled (pending confirmation from ESPHome)
        self._pending_fingerprint_id: int | None = None

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
        """Load persisted fingerprints and attach event/state listeners."""
        self._load_fingerprints()

        prefix = self._option_or_data(CONF_EVENT_PREFIX)
        if prefix:
            for suffix, handler in (
                (EVENT_SUFFIX_MATCHED, self._handle_scan_matched),
                (EVENT_SUFFIX_UNMATCHED, self._handle_scan_unmatched),
                (EVENT_SUFFIX_INVALID, self._handle_scan_invalid),
                (EVENT_SUFFIX_MISPLACED, self._handle_scan_misplaced),
                (EVENT_SUFFIX_ENROLLMENT_SCAN, self._handle_enrollment_scan),
                (EVENT_SUFFIX_ENROLLMENT_DONE, self._handle_enrollment_done),
                (EVENT_SUFFIX_ENROLLMENT_FAILED, self._handle_enrollment_failed),
            ):
                event_name = f"{prefix}{suffix}"
                unsub = self.hass.bus.async_listen(event_name, handler)
                self._unsub_listeners.append(unsub)
                _LOGGER.debug("Listening to HA event: %s", event_name)
        else:
            _LOGGER.warning(
                "No event_prefix configured for %s. "
                "Scan events will not be received. "
                "Set it in the integration options.",
                self.config_entry.entry_id,
            )

        # Optional: also monitor the fingerprint ID sensor for state changes.
        sensor_entity = self._option_or_data(CONF_SENSOR_ENTITY)
        if sensor_entity:
            unsub = async_track_state_change_event(
                self.hass,
                [sensor_entity],
                self._handle_sensor_state_change,
            )
            self._unsub_listeners.append(unsub)
            _LOGGER.debug("Also monitoring sensor entity: %s", sensor_entity)

        self.async_set_updated_data(self._build_snapshot())

    @callback
    def async_teardown(self) -> None:
        """Remove all listeners."""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _option_or_data(self, key: str) -> Any:
        """Return the option value if present, else fall back to config-entry data."""
        return self.config_entry.options.get(key) or self.config_entry.data.get(key)

    def _load_fingerprints(self) -> None:
        """Load fingerprints from the persisted config-entry options."""
        raw: dict[str, Any] = self.config_entry.options.get(FINGERPRINT_STORAGE, {})
        self._fingerprints = {
            int(fp_id): FingerprintEntry.from_dict(fp_data)
            for fp_id, fp_data in raw.items()
        }
        _LOGGER.debug("Loaded %d fingerprint mapping(s)", len(self._fingerprints))

    async def _save_fingerprints(self) -> None:
        """Persist the current fingerprint mappings in the config-entry options."""
        options = dict(self.config_entry.options)
        options[FINGERPRINT_STORAGE] = {
            str(fp_id): fp.to_dict() for fp_id, fp in self._fingerprints.items()
        }
        self.hass.config_entries.async_update_entry(self.config_entry, options=options)

    def _build_snapshot(self) -> dict[str, Any]:
        return {
            "status": self._status,
            "last_user": self._last_user,
            "last_fingerprint_id": self._last_fingerprint_id,
            "fingerprints": {
                fp_id: fp.to_dict() for fp_id, fp in self._fingerprints.items()
            },
        }

    # ── ESPHome event handlers ────────────────────────────────────────────────
    # Event data from ESPHome homeassistant.event uses lambda-generated values
    # which are always strings, even for numeric fields.

    @callback
    def _handle_scan_matched(self, event: Event) -> None:
        """Handle esphome.<prefix>_finger_scan_matched.

        Expected event data:
            finger_id  : str(int)   – matched slot id (e.g. "5")
            confidence : str(int)   – match confidence (e.g. "100")
        """
        finger_id = _parse_int(event.data.get("finger_id", 0))
        if finger_id < 1:
            _LOGGER.debug("scan_matched event with invalid finger_id=%s – ignored", event.data)
            return

        confidence = _parse_int(event.data.get("confidence", 0)) or None
        self._last_fingerprint_id = finger_id

        if finger_id in self._fingerprints:
            fp = self._fingerprints[finger_id]
            self._last_user = fp.user
            self._status = STATE_MATCHED
            matched = True
            _LOGGER.info("Matched: id=%d user=%s label=%s", finger_id, fp.user, fp.label)
        else:
            self._last_user = None
            self._status = STATE_UNKNOWN_FINGER
            matched = False
            _LOGGER.info("Unknown fingerprint: id=%d", finger_id)

        event_data: dict[str, Any] = {
            ATTR_FINGERPRINT_ID: finger_id,
            ATTR_USER: self._last_user,
            ATTR_LABEL: self._fingerprints[finger_id].label if matched else None,
            ATTR_MATCHED: matched,
            "config_entry_id": self.config_entry.entry_id,
        }
        if confidence is not None:
            event_data[ATTR_CONFIDENCE] = confidence

        self.hass.bus.async_fire(EVENT_FINGERPRINT_SCAN, event_data)
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_scan_unmatched(self, event: Event) -> None:  # noqa: ARG002
        """Handle esphome.<prefix>_finger_scan_unmatched."""
        self._last_user = None
        self._status = STATE_UNKNOWN_FINGER
        self.hass.bus.async_fire(
            EVENT_FINGERPRINT_SCAN,
            {
                ATTR_FINGERPRINT_ID: None,
                ATTR_USER: None,
                ATTR_LABEL: None,
                ATTR_MATCHED: False,
                "config_entry_id": self.config_entry.entry_id,
            },
        )
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_scan_invalid(self, event: Event) -> None:  # noqa: ARG002
        """Handle esphome.<prefix>_finger_scan_invalid.

        An invalid scan means the image quality was too poor to process.
        Update the status so the sensor reflects it; no scan event is fired
        because no finger ID is available.
        """
        _LOGGER.debug("Invalid finger scan received")
        self._status = "invalid_scan"
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_scan_misplaced(self, event: Event) -> None:  # noqa: ARG002
        """Handle esphome.<prefix>_finger_scan_misplaced.

        A misplaced scan means the finger was not placed correctly on the sensor.
        Update the status so the sensor reflects it; no scan event is fired
        because no finger ID is available.
        """
        _LOGGER.debug("Misplaced finger scan received")
        self._status = "finger_misplaced"
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_enrollment_scan(self, event: Event) -> None:
        """Handle esphome.<prefix>_enrollment_scan (intermediate enrollment scan).

        Expected event data:
            finger_id : str(int)
            scan_num  : str(int)  – which scan this is (1-based)
        """
        scan_num = _parse_int(event.data.get("scan_num", 0))
        _LOGGER.info("Enrollment scan %d received", scan_num)
        self._status = f"{STATE_ENROLLING}_{scan_num}"
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_enrollment_done(self, event: Event) -> None:
        """Handle esphome.<prefix>_enrollment_done.

        Expected event data:
            finger_id : str(int)  – the slot that was successfully enrolled
        """
        finger_id = _parse_int(event.data.get("finger_id", 0))
        _LOGGER.info("Enrollment done: id=%d", finger_id)

        self._pending_fingerprint_id = None
        self._status = STATE_IDLE

        fp = self._fingerprints.get(finger_id)
        self.hass.bus.async_fire(
            EVENT_FINGERPRINT_ENROLLED,
            {
                ATTR_FINGERPRINT_ID: finger_id,
                ATTR_USER: fp.user if fp else None,
                ATTR_LABEL: fp.label if fp else None,
                "config_entry_id": self.config_entry.entry_id,
            },
        )
        self.async_set_updated_data(self._build_snapshot())

    @callback
    def _handle_enrollment_failed(self, event: Event) -> None:
        """Handle esphome.<prefix>_enrollment_failed.

        Expected event data:
            finger_id : str(int)  – the slot whose enrollment failed
        """
        finger_id = _parse_int(event.data.get("finger_id", 0))
        _LOGGER.warning("Enrollment failed: id=%d", finger_id)

        # Remove the optimistic mapping that was stored on start_enrollment.
        self._fingerprints.pop(finger_id, None)
        self._pending_fingerprint_id = None
        self._status = STATE_IDLE

        self.hass.bus.async_fire(
            EVENT_FINGERPRINT_ENROLLMENT_FAILED,
            {
                ATTR_FINGERPRINT_ID: finger_id,
                "config_entry_id": self.config_entry.entry_id,
            },
        )
        # Save without the failed entry.
        self.hass.async_create_task(self._save_fingerprints())
        self.async_set_updated_data(self._build_snapshot())

    # ── Optional sensor state-change listener ─────────────────────────────────

    @callback
    def _handle_sensor_state_change(self, event: Event) -> None:
        """Handle state change from the ESPHome Fingerprint ID sensor.

        The ESPHome template publishes -1 for any non-match state and the real
        finger_id for a matched scan. Only a state change to a value >= 1 is
        treated as a new scan (preventing re-processing on HA restart).
        """
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None:
            return

        state_str = new_state.state
        if state_str in ("unavailable", "unknown", "", None):
            return

        finger_id = _parse_int(state_str)

        # Ignore no-match or unchanged values.
        old_str = old_state.state if old_state else None
        if state_str == old_str:
            return

        if finger_id < 1:
            # Sensor reset to -1 / 0 — clear last match unless enrolling.
            if self._status != STATE_ENROLLING and not self._status.startswith(STATE_ENROLLING):
                self._status = STATE_IDLE
                self._last_fingerprint_id = None
                self._last_user = None
                self.async_set_updated_data(self._build_snapshot())
            return

        # A positive ID arrived from the sensor; only act if we don't have a
        # matching finger_scan_matched event listener configured (avoid double processing).
        prefix = self._option_or_data(CONF_EVENT_PREFIX)
        if not prefix:
            # No event prefix set – use the sensor as the sole scan source.
            self._last_fingerprint_id = finger_id
            if finger_id in self._fingerprints:
                fp = self._fingerprints[finger_id]
                self._last_user = fp.user
                self._status = STATE_MATCHED
                matched = True
            else:
                self._last_user = None
                self._status = STATE_UNKNOWN_FINGER
                matched = False

            self.hass.bus.async_fire(
                EVENT_FINGERPRINT_SCAN,
                {
                    ATTR_FINGERPRINT_ID: finger_id,
                    ATTR_USER: self._last_user,
                    ATTR_LABEL: self._fingerprints[finger_id].label if matched else None,
                    ATTR_MATCHED: matched,
                    "config_entry_id": self.config_entry.entry_id,
                },
            )
            self.async_set_updated_data(self._build_snapshot())

    # ── Service handlers ──────────────────────────────────────────────────────

    async def async_start_enrollment(
        self, fingerprint_id: int, user: str, label: str = "", num_scans: int = 2
    ) -> None:
        """Start fingerprint enrollment.

        Pre-registers the mapping so it is recognised immediately if the
        on_enrollment_done event somehow arrives before this coroutine returns.
        The mapping is removed again in _handle_enrollment_failed if ESPHome
        reports a failure.
        """
        self._pending_fingerprint_id = fingerprint_id
        self._status = STATE_ENROLLING

        # Pre-register optimistically.
        self._fingerprints[fingerprint_id] = FingerprintEntry(
            fingerprint_id=fingerprint_id, user=user, label=label
        )
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_snapshot())

        # Call the ESPHome API action.
        # ESPHome action name  : enroll
        # ESPHome variable names: finger_id (int), num_scans (int)
        # HA service            : esphome.{device_name}_enroll
        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            try:
                await self.hass.services.async_call(
                    "esphome",
                    f"{esphome_device}_enroll",
                    {"finger_id": fingerprint_id, "num_scans": num_scans},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome enroll service: %s", err)

        _LOGGER.info(
            "Enrollment started: id=%d user=%s label=%s", fingerprint_id, user, label
        )

    async def async_cancel_enrollment(self) -> None:
        """Cancel the current enrollment and call the ESPHome cancel action."""
        self._pending_fingerprint_id = None
        self._status = STATE_IDLE

        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            try:
                await self.hass.services.async_call(
                    "esphome",
                    f"{esphome_device}_cancel_enroll",
                    {},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome cancel_enroll service: %s", err)

        self.async_set_updated_data(self._build_snapshot())

    async def async_delete_fingerprint(self, fingerprint_id: int) -> None:
        """Delete a fingerprint mapping and remove it from the ESPHome reader."""
        if fingerprint_id not in self._fingerprints:
            _LOGGER.warning("delete_fingerprint: ID %d not found", fingerprint_id)
            return

        del self._fingerprints[fingerprint_id]
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_snapshot())

        # ESPHome action name  : delete
        # ESPHome variable name: finger_id (int)
        # HA service            : esphome.{device_name}_delete
        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            try:
                await self.hass.services.async_call(
                    "esphome",
                    f"{esphome_device}_delete",
                    {"finger_id": fingerprint_id},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome delete service: %s", err)

        _LOGGER.info("Deleted fingerprint id=%d", fingerprint_id)

    async def async_delete_all_fingerprints(self) -> None:
        """Delete all fingerprint mappings and wipe the ESPHome reader."""
        self._fingerprints.clear()
        await self._save_fingerprints()
        self.async_set_updated_data(self._build_snapshot())

        # ESPHome action name: delete_all
        # HA service          : esphome.{device_name}_delete_all
        esphome_device = self._option_or_data(CONF_ESPHOME_DEVICE)
        if esphome_device:
            try:
                await self.hass.services.async_call(
                    "esphome",
                    f"{esphome_device}_delete_all",
                    {},
                    blocking=False,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("Could not call ESPHome delete_all service: %s", err)

        _LOGGER.info("Deleted all fingerprints")

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
        self.async_set_updated_data(self._build_snapshot())
        _LOGGER.info("Updated fingerprint id=%d", fingerprint_id)
