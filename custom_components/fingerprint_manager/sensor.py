"""Sensor platform for Fingerprint Manager."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import FingerprintManagerCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Fingerprint Manager sensor entities."""
    coordinator: FingerprintManagerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    async_add_entities(
        [
            FingerprintStatusSensor(coordinator, config_entry),
            FingerprintLastUserSensor(coordinator, config_entry),
        ]
    )


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="Fingerprint Manager",
        model="ESPHome Fingerprint Reader",
    )


class FingerprintStatusSensor(CoordinatorEntity, SensorEntity):
    """Sensor reporting the current status of the fingerprint reader."""

    _attr_has_entity_name = True
    _attr_name = "Status"
    _attr_icon = "mdi:fingerprint"

    def __init__(
        self, coordinator: FingerprintManagerCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_status"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str:
        return self.coordinator.status

    @property
    def extra_state_attributes(self) -> dict:
        """Expose all enrolled fingerprints as an attribute."""
        return {
            "fingerprints": [
                fp.to_dict()
                for fp in self.coordinator.fingerprints.values()
            ]
        }


class FingerprintLastUserSensor(CoordinatorEntity, SensorEntity):
    """Sensor reporting the last user who successfully scanned a fingerprint."""

    _attr_has_entity_name = True
    _attr_name = "Last User"
    _attr_icon = "mdi:account-check"

    def __init__(
        self, coordinator: FingerprintManagerCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_user"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> str | None:
        return self.coordinator.last_user

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "fingerprint_id": self.coordinator.last_fingerprint_id,
        }
