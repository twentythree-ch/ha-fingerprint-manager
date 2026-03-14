"""Tests for FingerprintManagerCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.fingerprint_manager.const import (
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_ENROLLMENT_FAILED,
    EVENT_FINGERPRINT_SCAN,
    EVENT_SUFFIX_ENROLLMENT_DONE,
    EVENT_SUFFIX_ENROLLMENT_FAILED,
    EVENT_SUFFIX_ENROLLMENT_SCAN,
    EVENT_SUFFIX_MATCHED,
    EVENT_SUFFIX_UNMATCHED,
    FINGERPRINT_STORAGE,
    STATE_ENROLLING,
    STATE_IDLE,
    STATE_MATCHED,
    STATE_UNKNOWN_FINGER,
)
from custom_components.fingerprint_manager.coordinator import (
    FingerprintEntry,
    FingerprintManagerCoordinator,
    _parse_int,
)

from .conftest import make_config_entry


# ── _parse_int ────────────────────────────────────────────────────────────────

class TestParseInt:
    def test_integer_input(self):
        assert _parse_int(5) == 5

    def test_string_integer(self):
        assert _parse_int("7") == 7

    def test_string_float(self):
        assert _parse_int("3.0") == 3

    def test_none_returns_default(self):
        assert _parse_int(None) == 0

    def test_non_numeric_returns_default(self):
        assert _parse_int("abc") == 0

    def test_custom_default(self):
        assert _parse_int("bad", default=-1) == -1


# ── FingerprintEntry ──────────────────────────────────────────────────────────

class TestFingerprintEntry:
    def test_to_dict(self):
        fp = FingerprintEntry(fingerprint_id=3, user="Alice", label="Left index")
        assert fp.to_dict() == {
            "fingerprint_id": 3,
            "user": "Alice",
            "label": "Left index",
        }

    def test_from_dict_with_label(self):
        fp = FingerprintEntry.from_dict(
            {"fingerprint_id": 5, "user": "Bob", "label": "Right thumb"}
        )
        assert fp.fingerprint_id == 5
        assert fp.user == "Bob"
        assert fp.label == "Right thumb"

    def test_from_dict_without_label_defaults_empty(self):
        fp = FingerprintEntry.from_dict({"fingerprint_id": 7, "user": "Carol"})
        assert fp.label == ""

    def test_from_dict_accepts_string_id(self):
        fp = FingerprintEntry.from_dict({"fingerprint_id": "10", "user": "Dave"})
        assert fp.fingerprint_id == 10

    def test_round_trip(self):
        fp = FingerprintEntry(fingerprint_id=10, user="Eve", label="Thumb")
        recovered = FingerprintEntry.from_dict(fp.to_dict())
        assert recovered.fingerprint_id == fp.fingerprint_id
        assert recovered.user == fp.user
        assert recovered.label == fp.label


# ── Coordinator setup ─────────────────────────────────────────────────────────

class TestCoordinatorSetup:
    async def test_loads_fingerprints_on_setup(self, hass, config_entry_with_fingerprints):
        coord = FingerprintManagerCoordinator(hass, config_entry_with_fingerprints)
        with patch(
            "custom_components.fingerprint_manager.coordinator.async_track_state_change_event",
            return_value=lambda: None,
        ):
            await coord.async_setup()

        assert len(coord.fingerprints) == 2
        assert coord.fingerprints[1].user == "Alice"
        assert coord.fingerprints[2].user == "Bob"

    async def test_setup_subscribes_to_all_event_suffixes(self, hass, config_entry):
        listened_events: list[str] = []
        hass.bus.async_listen = MagicMock(
            side_effect=lambda evt, cb: listened_events.append(evt) or (lambda: None)
        )
        with patch(
            "custom_components.fingerprint_manager.coordinator.async_track_state_change_event",
            return_value=lambda: None,
        ):
            coord = FingerprintManagerCoordinator(hass, config_entry)
            await coord.async_setup()

        prefix = "esphome.garage_fingerprint"
        from custom_components.fingerprint_manager.const import (
            EVENT_SUFFIX_INVALID,
            EVENT_SUFFIX_MISPLACED,
        )
        for suffix in (
            EVENT_SUFFIX_MATCHED,
            EVENT_SUFFIX_UNMATCHED,
            EVENT_SUFFIX_INVALID,
            EVENT_SUFFIX_MISPLACED,
            EVENT_SUFFIX_ENROLLMENT_SCAN,
            EVENT_SUFFIX_ENROLLMENT_DONE,
            EVENT_SUFFIX_ENROLLMENT_FAILED,
        ):
            assert f"{prefix}{suffix}" in listened_events

    async def test_setup_subscribes_to_sensor(self, hass, config_entry):
        tracked = []
        with patch(
            "custom_components.fingerprint_manager.coordinator.async_track_state_change_event",
            side_effect=lambda h, entities, cb: tracked.extend(entities) or (lambda: None),
        ):
            coord = FingerprintManagerCoordinator(hass, config_entry)
            await coord.async_setup()

        assert "sensor.garage_fingerprint_fingerprint_id" in tracked

    async def test_teardown_calls_all_unsubs(self, hass):
        unsub1, unsub2 = MagicMock(), MagicMock()
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._unsub_listeners = [unsub1, unsub2]

        coord.async_teardown()

        unsub1.assert_called_once()
        unsub2.assert_called_once()
        assert coord._unsub_listeners == []


# ── Scan matched event handler ────────────────────────────────────────────────

class TestHandleScanMatched:
    def _coord_with_fps(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._fingerprints = {
            5: FingerprintEntry(5, "Alice", "Left index"),
        }
        return coord

    def _event(self, finger_id, confidence=None):
        ev = MagicMock()
        ev.data = {"finger_id": str(finger_id)}
        if confidence is not None:
            ev.data["confidence"] = str(confidence)
        return ev

    def test_known_finger_sets_matched_status(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(5, 98))
        assert coord.status == STATE_MATCHED
        assert coord.last_user == "Alice"
        assert coord.last_fingerprint_id == 5

    def test_known_finger_fires_scan_event_with_user(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(5, 98))
        hass.bus.async_fire.assert_called_once()
        name, data = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_SCAN
        assert data["user"] == "Alice"
        assert data["matched"] is True
        assert data["confidence"] == 98

    def test_unknown_finger_sets_unknown_status(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(99))
        assert coord.status == STATE_UNKNOWN_FINGER
        assert coord.last_user is None

    def test_unknown_finger_fires_scan_event_unmatched(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(99))
        _, data = hass.bus.async_fire.call_args[0]
        assert data["matched"] is False
        assert data["user"] is None

    def test_zero_finger_id_ignored(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(0))
        hass.bus.async_fire.assert_not_called()

    def test_negative_finger_id_ignored(self, hass):
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(-1))
        hass.bus.async_fire.assert_not_called()

    def test_confidence_omitted_when_zero(self, hass):
        """Zero confidence → key should be absent from event data."""
        coord = self._coord_with_fps(hass)
        coord._handle_scan_matched(self._event(5))  # no confidence in event
        _, data = hass.bus.async_fire.call_args[0]
        assert "confidence" not in data


# ── Scan unmatched event handler ──────────────────────────────────────────────

class TestHandleScanUnmatched:
    def test_sets_unknown_status_and_fires_event(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        ev = MagicMock()
        ev.data = {}
        coord._handle_scan_unmatched(ev)
        assert coord.status == STATE_UNKNOWN_FINGER
        hass.bus.async_fire.assert_called_once()
        name, data = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_SCAN
        assert data["matched"] is False


# ── Invalid / misplaced scan event handlers ───────────────────────────────────

class TestHandleScanInvalidAndMisplaced:
    def test_invalid_scan_sets_status(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        ev = MagicMock()
        ev.data = {}
        coord._handle_scan_invalid(ev)
        assert coord.status == "invalid_scan"
        # No fingerprint_manager_scan event for invalid scans
        hass.bus.async_fire.assert_not_called()

    def test_misplaced_scan_sets_status(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        ev = MagicMock()
        ev.data = {}
        coord._handle_scan_misplaced(ev)
        assert coord.status == "finger_misplaced"
        # No fingerprint_manager_scan event for misplaced scans
        hass.bus.async_fire.assert_not_called()


# ── Enrollment scan event handler ─────────────────────────────────────────────

class TestHandleEnrollmentScan:
    def test_updates_status_with_scan_number(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._pending_fingerprint_id = 3
        ev = MagicMock()
        ev.data = {"finger_id": "3", "scan_num": "1"}
        coord._handle_enrollment_scan(ev)
        assert coord.status == "enrolling_1"

    def test_ignored_when_no_active_enrollment(self, hass):
        """A late enrollment_scan must not reset the status after enrollment_done."""
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        # Simulate enrollment already completed: pending cleared, status idle
        coord._pending_fingerprint_id = None
        coord._status = STATE_IDLE
        ev = MagicMock()
        ev.data = {"finger_id": "3", "scan_num": "2"}
        coord._handle_enrollment_scan(ev)
        # Status must NOT change back to enrolling
        assert coord.status == STATE_IDLE


# ── Enrollment done event handler ─────────────────────────────────────────────

class TestHandleEnrollmentDone:
    def test_sets_idle_and_fires_enrolled_event(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._fingerprints = {3: FingerprintEntry(3, "Frank", "Pinky")}
        coord._status = STATE_ENROLLING
        coord._pending_fingerprint_id = 3

        ev = MagicMock()
        ev.data = {"finger_id": "3"}
        coord._handle_enrollment_done(ev)

        assert coord.status == STATE_IDLE
        assert coord._pending_fingerprint_id is None
        hass.bus.async_fire.assert_called_once()
        name, data = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_ENROLLED
        assert data["user"] == "Frank"

    def test_fires_enrolled_event_even_if_no_mapping(self, hass):
        """ESPHome fired enrollment_done for a slot we don't know about."""
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        ev = MagicMock()
        ev.data = {"finger_id": "99"}
        coord._handle_enrollment_done(ev)
        name, data = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_ENROLLED
        assert data["user"] is None


# ── Enrollment failed event handler ───────────────────────────────────────────

class TestHandleEnrollmentFailed:
    def test_removes_optimistic_mapping_and_fires_failed_event(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._fingerprints = {7: FingerprintEntry(7, "Grace", "")}
        coord._pending_fingerprint_id = 7
        coord._status = STATE_ENROLLING

        ev = MagicMock()
        ev.data = {"finger_id": "7"}
        coord._handle_enrollment_failed(ev)

        assert 7 not in coord.fingerprints
        assert coord.status == STATE_IDLE
        assert coord._pending_fingerprint_id is None
        hass.bus.async_fire.assert_called_once()
        name, _ = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_ENROLLMENT_FAILED


# ── Sensor state-change listener ──────────────────────────────────────────────

class TestSensorStateChange:
    def _coord(self, hass, event_prefix=""):
        """Create a coordinator without an event_prefix so sensor is used as sole source."""
        entry = make_config_entry(data={
            "event_prefix": event_prefix,
            "esphome_device": "",
            "sensor_entity_id": "sensor.fp",
        })
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._fingerprints = {5: FingerprintEntry(5, "Eve", "Index")}
        return coord

    def _evt(self, new_val, old_val="0"):
        def _state(v):
            s = MagicMock()
            s.state = v
            return s
        ev = MagicMock()
        ev.data = {"new_state": _state(new_val), "old_state": _state(old_val)}
        return ev

    def test_valid_id_fires_scan_event_when_no_prefix(self, hass):
        coord = self._coord(hass, event_prefix="")
        coord._handle_sensor_state_change(self._evt("5"))
        hass.bus.async_fire.assert_called_once()
        name, data = hass.bus.async_fire.call_args[0]
        assert name == EVENT_FINGERPRINT_SCAN
        assert data["matched"] is True

    def test_negative_id_sets_idle(self, hass):
        coord = self._coord(hass, event_prefix="")
        coord._status = STATE_MATCHED
        coord._handle_sensor_state_change(self._evt("-1", "5"))
        assert coord.status == STATE_IDLE

    def test_unavailable_state_ignored(self, hass):
        coord = self._coord(hass, event_prefix="")
        coord._handle_sensor_state_change(self._evt("unavailable"))
        hass.bus.async_fire.assert_not_called()

    def test_duplicate_state_not_reprocessed(self, hass):
        coord = self._coord(hass, event_prefix="")
        coord._handle_sensor_state_change(self._evt("5", "5"))
        hass.bus.async_fire.assert_not_called()

    def test_sensor_does_not_fire_when_event_prefix_set(self, hass):
        """When event_prefix is configured the sensor should not duplicate scans."""
        coord = self._coord(hass, event_prefix="esphome.garage_fingerprint")
        coord._handle_sensor_state_change(self._evt("5"))
        hass.bus.async_fire.assert_not_called()


# ── CRUD services ─────────────────────────────────────────────────────────────

class TestCRUD:
    async def test_start_enrollment_registers_mapping_immediately(self, hass):
        entry = make_config_entry(data={"event_prefix": "", "esphome_device": ""})
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_start_enrollment(10, "Grace", "Pinky")

        assert 10 in coord.fingerprints
        assert coord.fingerprints[10].user == "Grace"
        assert coord.fingerprints[10].label == "Pinky"
        assert coord.status == STATE_ENROLLING

    async def test_start_enrollment_calls_esphome_service(self, hass):
        entry = make_config_entry(data={
            "event_prefix": "esphome.garage_fingerprint",
            "esphome_device": "esphome_garage_fingerprint",
        })
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_start_enrollment(3, "Heidi", num_scans=3)

        hass.services.async_call.assert_called_once_with(
            "esphome",
            "esphome_garage_fingerprint_enroll",
            {"finger_id": 3, "num_scans": 3},
            blocking=False,
        )

    async def test_cancel_enrollment_resets_status(self, hass):
        entry = make_config_entry(data={"event_prefix": "", "esphome_device": ""})
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._status = STATE_ENROLLING

        await coord.async_cancel_enrollment()

        assert coord.status == STATE_IDLE

    async def test_cancel_enrollment_calls_esphome_service(self, hass):
        entry = make_config_entry(data={
            "event_prefix": "",
            "esphome_device": "esphome_garage_fingerprint",
        })
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_cancel_enrollment()

        hass.services.async_call.assert_called_once_with(
            "esphome",
            "esphome_garage_fingerprint_cancel_enroll",
            {},
            blocking=False,
        )

    async def test_delete_fingerprint_removes_mapping(self, hass):
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {
                    "5": {"fingerprint_id": 5, "user": "Heidi", "label": ""}
                }
            },
            data={"event_prefix": "", "esphome_device": ""},
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_delete_fingerprint(5)

        assert 5 not in coord.fingerprints

    async def test_delete_fingerprint_calls_esphome_service(self, hass):
        entry = make_config_entry(
            options={FINGERPRINT_STORAGE: {"5": {"fingerprint_id": 5, "user": "Ivan", "label": ""}}},
            data={"event_prefix": "", "esphome_device": "esphome_garage_fingerprint"},
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_delete_fingerprint(5)

        hass.services.async_call.assert_called_once_with(
            "esphome",
            "esphome_garage_fingerprint_delete",
            {"finger_id": 5},
            blocking=False,
        )

    async def test_delete_nonexistent_fingerprint_is_noop(self, hass):
        entry = make_config_entry(data={"event_prefix": "", "esphome_device": ""})
        coord = FingerprintManagerCoordinator(hass, entry)
        await coord.async_delete_fingerprint(99)  # must not raise

    async def test_delete_all_clears_all_mappings(self, hass):
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {
                    "1": {"fingerprint_id": 1, "user": "A", "label": ""},
                    "2": {"fingerprint_id": 2, "user": "B", "label": ""},
                }
            },
            data={"event_prefix": "", "esphome_device": ""},
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_delete_all_fingerprints()

        assert coord.fingerprints == {}

    async def test_delete_all_calls_esphome_service(self, hass):
        entry = make_config_entry(
            data={"event_prefix": "", "esphome_device": "esphome_garage_fingerprint"}
        )
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_delete_all_fingerprints()

        hass.services.async_call.assert_called_once_with(
            "esphome",
            "esphome_garage_fingerprint_delete_all",
            {},
            blocking=False,
        )

    async def test_update_changes_user(self, hass):
        entry = make_config_entry(
            options={FINGERPRINT_STORAGE: {"3": {"fingerprint_id": 3, "user": "Ivan", "label": ""}}},
            data={"event_prefix": "", "esphome_device": ""},
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_update_fingerprint(3, user="Ivan Updated")

        assert coord.fingerprints[3].user == "Ivan Updated"

    async def test_update_changes_label_without_touching_user(self, hass):
        entry = make_config_entry(
            options={FINGERPRINT_STORAGE: {"3": {"fingerprint_id": 3, "user": "Judy", "label": "old"}}},
            data={"event_prefix": "", "esphome_device": ""},
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_update_fingerprint(3, label="New label")

        assert coord.fingerprints[3].label == "New label"
        assert coord.fingerprints[3].user == "Judy"

    async def test_update_nonexistent_is_noop(self, hass):
        entry = make_config_entry(data={"event_prefix": "", "esphome_device": ""})
        coord = FingerprintManagerCoordinator(hass, entry)
        await coord.async_update_fingerprint(42, user="Nobody")  # must not raise
