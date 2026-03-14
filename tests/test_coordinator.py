"""Tests for FingerprintManagerCoordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from custom_components.fingerprint_manager.const import (
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_SCAN,
    FINGERPRINT_STORAGE,
    STATE_ENROLLING,
    STATE_IDLE,
    STATE_MATCHED,
    STATE_UNKNOWN_FINGER,
)
from custom_components.fingerprint_manager.coordinator import (
    FingerprintEntry,
    FingerprintManagerCoordinator,
)

from .conftest import make_config_entry


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
        data = {"fingerprint_id": 5, "user": "Bob", "label": "Right thumb"}
        fp = FingerprintEntry.from_dict(data)
        assert fp.fingerprint_id == 5
        assert fp.user == "Bob"
        assert fp.label == "Right thumb"

    def test_from_dict_without_label(self):
        data = {"fingerprint_id": 7, "user": "Carol"}
        fp = FingerprintEntry.from_dict(data)
        assert fp.label == ""

    def test_round_trip(self):
        fp = FingerprintEntry(fingerprint_id=10, user="Dave", label="Thumb")
        assert FingerprintEntry.from_dict(fp.to_dict()).user == "Dave"


# ── Coordinator setup ─────────────────────────────────────────────────────────

class TestCoordinatorSetup:
    @pytest.mark.asyncio
    async def test_loads_fingerprints_on_setup(self, hass, config_entry_with_fingerprints):
        coord = FingerprintManagerCoordinator(hass, config_entry_with_fingerprints)

        with patch.object(hass.bus, "async_listen", return_value=lambda: None):
            with patch(
                "custom_components.fingerprint_manager.coordinator.async_track_state_change_event",
                return_value=lambda: None,
            ):
                await coord.async_setup()

        assert len(coord.fingerprints) == 2
        assert coord.fingerprints[1].user == "Alice"
        assert coord.fingerprints[2].user == "Bob"

    @pytest.mark.asyncio
    async def test_setup_subscribes_to_event_and_sensor(self, hass, config_entry):
        listen_calls = []
        sensor_unsub_calls = []

        hass.bus.async_listen = MagicMock(
            side_effect=lambda evt, cb: listen_calls.append(evt) or (lambda: None)
        )

        with patch(
            "custom_components.fingerprint_manager.coordinator.async_track_state_change_event",
            side_effect=lambda h, entities, cb: sensor_unsub_calls.append(entities)
            or (lambda: None),
        ):
            coord = FingerprintManagerCoordinator(hass, config_entry)
            await coord.async_setup()

        assert any("fingerprint_scan" in e for e in listen_calls)
        assert sensor_unsub_calls  # sensor subscription was registered


# ── Scan processing ───────────────────────────────────────────────────────────

class TestScanProcessing:
    def _make_coordinator(self, hass, options=None):
        entry = make_config_entry(options=options or {})
        coord = FingerprintManagerCoordinator(hass, entry)
        return coord

    def _load_fingerprints(self, coord):
        """Helper: manually load two fingerprints."""
        coord._fingerprints = {
            1: FingerprintEntry(1, "Alice", "Left index"),
            2: FingerprintEntry(2, "Bob", "Right thumb"),
        }

    def test_known_fingerprint_sets_matched_status(self, hass):
        coord = self._make_coordinator(hass)
        self._load_fingerprints(coord)

        coord._process_scan(1)

        assert coord.status == STATE_MATCHED
        assert coord.last_user == "Alice"
        assert coord.last_fingerprint_id == 1

    def test_known_fingerprint_fires_scan_event(self, hass):
        coord = self._make_coordinator(hass)
        self._load_fingerprints(coord)

        coord._process_scan(1)

        hass.bus.async_fire.assert_called_once()
        event_name, event_data = hass.bus.async_fire.call_args[0]
        assert event_name == EVENT_FINGERPRINT_SCAN
        assert event_data["user"] == "Alice"
        assert event_data["matched"] is True

    def test_unknown_fingerprint_sets_unknown_status(self, hass):
        coord = self._make_coordinator(hass)
        self._load_fingerprints(coord)

        coord._process_scan(99)

        assert coord.status == STATE_UNKNOWN_FINGER
        assert coord.last_user is None

    def test_unknown_fingerprint_fires_scan_event_unmatched(self, hass):
        coord = self._make_coordinator(hass)
        self._load_fingerprints(coord)

        coord._process_scan(99)

        hass.bus.async_fire.assert_called_once()
        _, event_data = hass.bus.async_fire.call_args[0]
        assert event_data["matched"] is False
        assert event_data["user"] is None

    def test_confidence_included_when_provided(self, hass):
        coord = self._make_coordinator(hass)
        self._load_fingerprints(coord)

        coord._process_scan(1, confidence=98)

        _, event_data = hass.bus.async_fire.call_args[0]
        assert event_data["confidence"] == 98


# ── Sensor state-change handler ───────────────────────────────────────────────

class TestSensorStateChange:
    def _coord_with_fingerprints(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._fingerprints = {
            5: FingerprintEntry(5, "Eve", "Index"),
        }
        return coord

    def _make_event(self, new_state_value, old_state_value="0"):
        def make_state(val):
            s = MagicMock()
            s.state = val
            return s

        event = MagicMock()
        event.data = {
            "new_state": make_state(new_state_value),
            "old_state": make_state(old_state_value),
        }
        return event

    def test_valid_state_triggers_process_scan(self, hass):
        coord = self._coord_with_fingerprints(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_sensor_state_change(self._make_event("5"))

        process.assert_called_once_with(5)

    def test_zero_state_sets_idle(self, hass):
        coord = self._coord_with_fingerprints(hass)
        coord._status = STATE_MATCHED

        coord._handle_sensor_state_change(self._make_event("0", "5"))

        assert coord.status == STATE_IDLE

    def test_unavailable_state_ignored(self, hass):
        coord = self._coord_with_fingerprints(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_sensor_state_change(self._make_event("unavailable"))

        process.assert_not_called()

    def test_duplicate_state_not_reprocessed(self, hass):
        coord = self._coord_with_fingerprints(hass)
        process = MagicMock()
        coord._process_scan = process

        # old and new state are the same
        coord._handle_sensor_state_change(self._make_event("5", "5"))

        process.assert_not_called()


# ── ESPHome event handler ─────────────────────────────────────────────────────

class TestESPHomeEventHandler:
    def _coord(self, hass):
        coord = FingerprintManagerCoordinator(hass, make_config_entry())
        coord._fingerprints = {3: FingerprintEntry(3, "Frank", "")}
        return coord

    def _make_event(self, data):
        event = MagicMock()
        event.data = data
        return event

    def test_handles_integer_finger_id(self, hass):
        coord = self._coord(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_esphome_event(self._make_event({"finger_id": 3, "matched": "true"}))

        process.assert_called_once_with(3, None)

    def test_handles_string_finger_id(self, hass):
        coord = self._coord(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_esphome_event(self._make_event({"finger_id": "3", "confidence": "100"}))

        process.assert_called_once_with(3, 100)

    def test_zero_finger_id_ignored(self, hass):
        coord = self._coord(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_esphome_event(self._make_event({"finger_id": 0}))

        process.assert_not_called()

    def test_missing_finger_id_ignored(self, hass):
        coord = self._coord(hass)
        process = MagicMock()
        coord._process_scan = process

        coord._handle_esphome_event(self._make_event({}))

        process.assert_not_called()


# ── CRUD services ─────────────────────────────────────────────────────────────

class TestCRUD:
    @pytest.mark.asyncio
    async def test_start_enrollment_adds_fingerprint(self, hass):
        entry = make_config_entry(data={})  # no ESPHome device
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_start_enrollment(10, "Grace", "Pinky")

        assert 10 in coord.fingerprints
        assert coord.fingerprints[10].user == "Grace"
        assert coord.fingerprints[10].label == "Pinky"
        assert coord.status == STATE_ENROLLING

    @pytest.mark.asyncio
    async def test_start_enrollment_fires_enrolled_event(self, hass):
        entry = make_config_entry(data={})
        coord = FingerprintManagerCoordinator(hass, entry)

        await coord.async_start_enrollment(10, "Grace")

        hass.bus.async_fire.assert_called_once()
        event_name, _ = hass.bus.async_fire.call_args[0]
        assert event_name == EVENT_FINGERPRINT_ENROLLED

    @pytest.mark.asyncio
    async def test_cancel_enrollment_resets_status(self, hass):
        entry = make_config_entry(data={})
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._status = STATE_ENROLLING

        await coord.async_cancel_enrollment()

        assert coord.status == STATE_IDLE

    @pytest.mark.asyncio
    async def test_delete_fingerprint_removes_entry(self, hass):
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {
                    "5": {"fingerprint_id": 5, "user": "Heidi", "label": ""}
                }
            }
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_delete_fingerprint(5)

        assert 5 not in coord.fingerprints

    @pytest.mark.asyncio
    async def test_delete_nonexistent_fingerprint_is_noop(self, hass):
        entry = make_config_entry(data={})
        coord = FingerprintManagerCoordinator(hass, entry)

        # Should not raise
        await coord.async_delete_fingerprint(99)

    @pytest.mark.asyncio
    async def test_update_fingerprint_changes_user(self, hass):
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {
                    "3": {"fingerprint_id": 3, "user": "Ivan", "label": ""}
                }
            }
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_update_fingerprint(3, user="Ivan Updated")

        assert coord.fingerprints[3].user == "Ivan Updated"

    @pytest.mark.asyncio
    async def test_update_fingerprint_changes_label(self, hass):
        entry = make_config_entry(
            options={
                FINGERPRINT_STORAGE: {
                    "3": {"fingerprint_id": 3, "user": "Judy", "label": "old"}
                }
            }
        )
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._load_fingerprints()

        await coord.async_update_fingerprint(3, label="New label")

        assert coord.fingerprints[3].label == "New label"
        assert coord.fingerprints[3].user == "Judy"  # unchanged

    @pytest.mark.asyncio
    async def test_update_nonexistent_fingerprint_is_noop(self, hass):
        entry = make_config_entry(data={})
        coord = FingerprintManagerCoordinator(hass, entry)

        # Should not raise
        await coord.async_update_fingerprint(42, user="Nobody")

    @pytest.mark.asyncio
    async def test_teardown_clears_listeners(self, hass):
        unsub = MagicMock()
        entry = make_config_entry(data={})
        coord = FingerprintManagerCoordinator(hass, entry)
        coord._unsub_listeners = [unsub, unsub]

        coord.async_teardown()

        assert unsub.call_count == 2
        assert coord._unsub_listeners == []
