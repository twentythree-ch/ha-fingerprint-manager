"""Tests for Fingerprint Manager device triggers."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from custom_components.fingerprint_manager.const import (
    ATTR_MATCHED,
    DOMAIN,
    EVENT_FINGERPRINT_ENROLLED,
    EVENT_FINGERPRINT_ENROLLMENT_FAILED,
    EVENT_FINGERPRINT_SCAN,
)
from custom_components.fingerprint_manager.device_trigger import (
    TRIGGER_TYPE_ENROLLMENT_FAILED,
    TRIGGER_TYPE_FINGERPRINT_ENROLLED,
    TRIGGER_TYPE_FINGERPRINT_MATCHED,
    TRIGGER_TYPE_FINGERPRINT_SCANNED,
    TRIGGER_TYPES,
    async_attach_trigger,
    async_get_triggers,
)

from .conftest import make_config_entry

ENTRY_ID = "test_entry_id"


def _make_hass(config_entry_id: str = ENTRY_ID) -> MagicMock:
    """Minimal mock HomeAssistant with enough surface for the trigger tests."""
    hass = MagicMock()
    hass.bus = MagicMock()

    # async_listen returns a plain callable that acts as the unsubscribe function
    _listeners: dict[str, Any] = {}

    def _listen(event_type, handler):
        _listeners[event_type] = handler
        return lambda: _listeners.pop(event_type, None)

    hass.bus.async_listen = MagicMock(side_effect=_listen)
    hass.bus.async_fire = MagicMock()
    hass._listeners = _listeners
    hass.async_create_task = MagicMock()
    return hass


def _make_dev_reg(config_entry_id: str = ENTRY_ID) -> MagicMock:
    """Return a mock device registry that resolves device_id to a known device."""
    device = MagicMock()
    device.identifiers = {(DOMAIN, config_entry_id)}

    dev_reg = MagicMock()
    dev_reg.async_get = MagicMock(return_value=device)
    return dev_reg


def _make_event(event_data: dict) -> MagicMock:
    ev = MagicMock()
    ev.data = event_data
    return ev


# ── async_get_triggers ────────────────────────────────────────────────────────


class TestAsyncGetTriggers:
    async def test_returns_all_trigger_types(self):
        hass = MagicMock()
        device_id = "device_abc"
        triggers = await async_get_triggers(hass, device_id)
        returned_types = {t["type"] for t in triggers}
        assert returned_types == TRIGGER_TYPES

    async def test_trigger_has_required_fields(self):
        hass = MagicMock()
        triggers = await async_get_triggers(hass, "device_xyz")
        for trigger in triggers:
            assert trigger["platform"] == "device"
            assert trigger["domain"] == DOMAIN
            assert trigger["device_id"] == "device_xyz"
            assert "type" in trigger


# ── async_attach_trigger ──────────────────────────────────────────────────────


class TestAsyncAttachTrigger:
    def _config(self, trigger_type: str, device_id: str = "dev1") -> dict:
        return {
            "platform": "device",
            "domain": DOMAIN,
            "device_id": device_id,
            "type": trigger_type,
        }

    def _trigger_info(self) -> dict:
        return {"trigger_data": {}}

    async def test_returns_unsubscribe_callable(self):
        hass = _make_hass()
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(),
        ):
            unsub = await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_FINGERPRINT_SCANNED),
                MagicMock(),
                self._trigger_info(),
            )
        assert callable(unsub)

    async def test_scanned_fires_on_any_scan_event(self):
        hass = _make_hass()
        action = MagicMock(return_value=None)
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(),
        ):
            await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_FINGERPRINT_SCANNED),
                action,
                self._trigger_info(),
            )

        # Simulate firing the fingerprint_scan event (matched=False)
        handler = hass._listeners[EVENT_FINGERPRINT_SCAN]
        ev = _make_event(
            {ATTR_MATCHED: False, "config_entry_id": ENTRY_ID}
        )
        handler(ev)
        hass.async_create_task.assert_called_once()

    async def test_matched_fires_only_on_matched_scan(self):
        hass = _make_hass()
        action = MagicMock(return_value=None)
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(),
        ):
            await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_FINGERPRINT_MATCHED),
                action,
                self._trigger_info(),
            )

        handler = hass._listeners[EVENT_FINGERPRINT_SCAN]

        # Unmatched scan – should NOT fire
        handler(_make_event({ATTR_MATCHED: False, "config_entry_id": ENTRY_ID}))
        hass.async_create_task.assert_not_called()

        # Matched scan – should fire
        handler(_make_event({ATTR_MATCHED: True, "config_entry_id": ENTRY_ID}))
        hass.async_create_task.assert_called_once()

    async def test_enrolled_fires_on_enrollment_done_event(self):
        hass = _make_hass()
        action = MagicMock(return_value=None)
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(),
        ):
            await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_FINGERPRINT_ENROLLED),
                action,
                self._trigger_info(),
            )

        handler = hass._listeners[EVENT_FINGERPRINT_ENROLLED]
        handler(_make_event({"fingerprint_id": 3, "config_entry_id": ENTRY_ID}))
        hass.async_create_task.assert_called_once()

    async def test_enrollment_failed_fires_on_failed_event(self):
        hass = _make_hass()
        action = MagicMock(return_value=None)
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(),
        ):
            await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_ENROLLMENT_FAILED),
                action,
                self._trigger_info(),
            )

        handler = hass._listeners[EVENT_FINGERPRINT_ENROLLMENT_FAILED]
        handler(_make_event({"fingerprint_id": 3, "config_entry_id": ENTRY_ID}))
        hass.async_create_task.assert_called_once()

    async def test_filters_events_from_other_devices(self):
        """Events with a different config_entry_id must not fire the trigger."""
        hass = _make_hass()
        action = MagicMock(return_value=None)
        with patch(
            "custom_components.fingerprint_manager.device_trigger.dr.async_get",
            return_value=_make_dev_reg(config_entry_id=ENTRY_ID),
        ):
            await async_attach_trigger(
                hass,
                self._config(TRIGGER_TYPE_FINGERPRINT_SCANNED),
                action,
                self._trigger_info(),
            )

        handler = hass._listeners[EVENT_FINGERPRINT_SCAN]
        handler(
            _make_event(
                {ATTR_MATCHED: True, "config_entry_id": "some_other_entry_id"}
            )
        )
        hass.async_create_task.assert_not_called()
